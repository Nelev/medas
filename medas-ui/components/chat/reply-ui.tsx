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

// The types the assistant prompt lists, and no others: a spec naming anything
// else fails validation below. Keep in step with the table in
// medas-api/langchain_agent/assistant_general_prompt.py.
const catalog = defineCatalog(schema, {
  components: {
    Card: defs.Card,
    Stack: defs.Stack,
    Text: defs.Text,
    Table: defs.Table,
    Alert: defs.Alert,
  },
  actions: {},
})

const { registry } = defineRegistry(catalog, {
  components: {
    Card: shadcnComponents.Card,
    Stack: shadcnComponents.Stack,
    Text: shadcnComponents.Text,
    Table: shadcnComponents.Table,
    Alert: shadcnComponents.Alert,
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
