"use client"

import { defineCatalog, type Spec } from "@json-render/core"
import {
  defineRegistry,
  JSONUIProvider,
  Renderer,
  schema,
} from "@json-render/react"
import { shadcnComponents } from "@json-render/shadcn"
import { shadcnComponentDefinitions as defs } from "@json-render/shadcn/catalog"
import { useMemo } from "react"

// The display components of json-render's shadcn set, and no others: a spec
// naming anything else fails validation below. Left out on purpose: Image,
// Avatar and Link, which load or follow a URL the model chose, from a record
// that can carry injected text; the form, button, dialog and menu components,
// which need actions and state this read-only reply does not have; and Tabs,
// which needs bound state; and Carousel, which swipes inside a chat bubble and
// needs a browser to draw. Keep in step with the table in
// medas-api/langchain_agent/assistant_general_prompt.py.
const catalog = defineCatalog(schema, {
  components: {
    Card: defs.Card,
    Stack: defs.Stack,
    Grid: defs.Grid,
    Separator: defs.Separator,
    Collapsible: defs.Collapsible,
    Accordion: defs.Accordion,
    Table: defs.Table,
    Heading: defs.Heading,
    Text: defs.Text,
    Badge: defs.Badge,
    Alert: defs.Alert,
    Progress: defs.Progress,
  },
  actions: {},
})

const { registry } = defineRegistry(catalog, {
  components: {
    Card: shadcnComponents.Card,
    Stack: shadcnComponents.Stack,
    Grid: shadcnComponents.Grid,
    Separator: shadcnComponents.Separator,
    Collapsible: shadcnComponents.Collapsible,
    Accordion: shadcnComponents.Accordion,
    Table: shadcnComponents.Table,
    Heading: shadcnComponents.Heading,
    Text: shadcnComponents.Text,
    Badge: shadcnComponents.Badge,
    Alert: shadcnComponents.Alert,
    Progress: shadcnComponents.Progress,
  },
})

// The layout an assistant turn may carry under its text. The spec is model
// output stored as-is, so it is validated here and dropped if it does not
// fit: the text is shown either way.
export function ReplyUI({ spec }: { spec: unknown }) {
  // Memoised on the spec, which the store keeps by reference: the list
  // re-renders on every send, and each validation walks the whole tree.
  const result = useMemo(() => catalog.validate(spec), [spec])

  if (!result.success) {
    return null
  }

  return (
    // The spacing lives here, so a dropped spec leaves no gap behind.
    <div className="mt-2">
      {/* Renderer reads state and visibility contexts even for a static
          spec. What is drawn is what validation parsed; the cast is only
          because the library's inferred spec type does not line up with the
          Spec its Renderer takes. */}
      <JSONUIProvider registry={registry}>
        <Renderer spec={result.data as Spec} registry={registry} />
      </JSONUIProvider>
    </div>
  )
}
