# Third-Party Notices

NEXUS bundles or depends on the following open-source projects:

## DeepSeek Harness (`@deepseek-ai/dsh`)

- License: MIT
- Copyright: DeepSeek AI
- Source: https://github.com/deepseek-ai/deepseek-harness
- Bundled version: `0.2.1-rc.2` (see `scripts/prepare_vendor.py`)

DeepSeek Harness is distributed in `vendor/dsh` together with its npm
dependencies. Their respective licenses are included in each package under
`vendor/dsh/node_modules/*/LICENSE*`.

## Node.js

- License: MIT and third-party licenses
- Copyright: Node.js contributors
- Source: https://nodejs.org
- Bundled binary: `vendor/node/node.exe`

## NiceGUI

- License: MIT
- Source: https://github.com/zauberzeug/nicegui
- Installed as a Python dependency.

## Other Python dependencies

See `requirements.txt` and `requirements-build.txt`. Each package retains its
own license in the Python environment used to build the executable.
