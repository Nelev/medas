# medas-ui

The frontend: the chat interface.

Setup, the environment variables, testing and troubleshooting all live in the
[root README](../README.md) — kept in one place so the two packages cannot
document the same contract differently.

```bash
yarn install                        # install
yarn dev                            # run, on :3000
yarn lint && yarn tsc --noEmit && yarn test
```

The UI talks to `medas-api`, so start that first — `yarn dev` alone renders an
error where the greeting should be.
