# Changelog

## [0.4.6](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.4.5...mud_server-v0.4.6) (2026-03-01)


### Features

* **api:** add world-prompts endpoint and prompt override to lab translate ([#155](https://github.com/pipe-works/pipeworks_mud_server/issues/155)) ([0e9525f](https://github.com/pipe-works/pipeworks_mud_server/commit/0e9525f9e75c6134f2abfa68739ba1cb22a1fb08))

## [0.4.5](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.4.4...mud_server-v0.4.5) (2026-03-01)


### Bug Fixes

* **translation:** add keep_alive to OllamaRenderer and increase pipeworks_web timeout ([#153](https://github.com/pipe-works/pipeworks_mud_server/issues/153)) ([8e14dd1](https://github.com/pipe-works/pipeworks_mud_server/commit/8e14dd14a3efeb7bf154eb36f13507828294bb10))

## [0.4.4](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.4.3...mud_server-v0.4.4) (2026-02-28)


### Bug Fixes

* **api:** resolve world_id key mismatch in lab worlds endpoint ([#151](https://github.com/pipe-works/pipeworks_mud_server/issues/151)) ([4a323c9](https://github.com/pipe-works/pipeworks_mud_server/commit/4a323c958ea9fb1e8c22c60a410dc458c6833e35))

## [0.4.3](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.4.2...mud_server-v0.4.3) (2026-02-28)


### Bug Fixes

* **build:** consolidate deps on pyproject.toml and automate version ([788e9bc](https://github.com/pipe-works/pipeworks_mud_server/commit/788e9bcdcee6de9bd210f0f5315faa340aa436bb))
* **build:** consolidate deps on pyproject.toml and automate version ([3c0eb2f](https://github.com/pipe-works/pipeworks_mud_server/commit/3c0eb2fcb59a560a4dbc4b2573f60f00edab8922))

## [0.4.2](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.4.1...mud_server-v0.4.2) (2026-02-28)


### Features

* **lab:** add lab API endpoints for Axis Descriptor Lab integration ([bbee9e7](https://github.com/pipe-works/pipeworks_mud_server/commit/bbee9e737f15e6a8b1ee7f275711d4251110a90f))
* **lab:** add lab API endpoints for Axis Descriptor Lab integration ([060c91f](https://github.com/pipe-works/pipeworks_mud_server/commit/060c91f43bfe5e89ce2208ec8dfeaa7c2b9e78d0))


### Bug Fixes

* **lab:** resolve ruff B904 and I001 lint errors ([436bbcc](https://github.com/pipe-works/pipeworks_mud_server/commit/436bbcc73ed72edb5ebd9e79e9948ddaf6fe89ca))

## [0.4.1](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.4.0...mud_server-v0.4.1) (2026-02-27)


### Bug Fixes

* **translation:** resolve {{profile_summary}} placeholder in OOC→IC pipeline ([#145](https://github.com/pipe-works/pipeworks_mud_server/issues/145)) ([ef0a37d](https://github.com/pipe-works/pipeworks_mud_server/commit/ef0a37d78026c5bd7e1d441b5f07c5f09324b0c9))

## [0.4.0](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.3.11...mud_server-v0.4.0) (2026-02-27)


### Features

* **axis:** implement axis resolution engine (Phase 3) ([9e43b0e](https://github.com/pipe-works/pipeworks_mud_server/commit/9e43b0ef214e739aa49b9bbe2d66414e35c5fe71))
* **axis:** implement axis resolution engine (Phase 3) ([3f66aa9](https://github.com/pipe-works/pipeworks_mud_server/commit/3f66aa9a858c217132c0a9e03c6f4ac64046ddd4))
* **engine:** wire axis engine to chat/yell/whisper (Phase 4) ([#143](https://github.com/pipe-works/pipeworks_mud_server/issues/143)) ([ffd71bb](https://github.com/pipe-works/pipeworks_mud_server/commit/ffd71bb0282bb28062be634c1263e282a1c2647e))
* **ledger:** add JSONL ledger writer and daily_undertaking resolution grammar ([308af12](https://github.com/pipe-works/pipeworks_mud_server/commit/308af129d8801fc12b7d3d6c7a52e6af65bad25d))
* **ledger:** JSONL ledger writer + daily_undertaking resolution grammar ([9b36e6f](https://github.com/pipe-works/pipeworks_mud_server/commit/9b36e6f05e7ff1c8537274e9d9c34c7c0821d977))
* **translation:** wire FUTURE(ledger) stubs to emit chat.translation events ([163101f](https://github.com/pipe-works/pipeworks_mud_server/commit/163101fb7ce6f56ca0b2a5fa1df0567405e78789))
* **translation:** wire FUTURE(ledger) stubs to emit chat.translation events ([70e208a](https://github.com/pipe-works/pipeworks_mud_server/commit/70e208a9ed19c9edeaff9624dbf75ff562c6f1de))


### Bug Fixes

* **ledger:** resolve ruff lint errors in test_writer.py ([23156d5](https://github.com/pipe-works/pipeworks_mud_server/commit/23156d5dccaa5106c7f097b5be508348e040b430))
* **world:** correct health and physique axis label orderings ([#138](https://github.com/pipe-works/pipeworks_mud_server/issues/138)) ([8fdc6c7](https://github.com/pipe-works/pipeworks_mud_server/commit/8fdc6c7e931e90a00e68a44bfbff77fa894cafd8))


### Miscellaneous Chores

* override release version to 0.4.0 ([#144](https://github.com/pipe-works/pipeworks_mud_server/issues/144)) ([b1bc648](https://github.com/pipe-works/pipeworks_mud_server/commit/b1bc648004cbc0c6c5ef164b1283208789782591))

## [0.3.11](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.3.10...mud_server-v0.3.11) (2026-02-26)


### Features

* **play:** wire command input, output window, and chat polling ([#135](https://github.com/pipe-works/pipeworks_mud_server/issues/135)) ([688f6da](https://github.com/pipe-works/pipeworks_mud_server/commit/688f6daa92ea875fb315365d1f72dbb098c15150))
* **translation:** add OOC→IC translation layer ([#136](https://github.com/pipe-works/pipeworks_mud_server/issues/136)) ([e7a263a](https://github.com/pipe-works/pipeworks_mud_server/commit/e7a263a5de1f583124bcffd6ff8ff325b4c6e360))
* **web:** migrate admin CSS to pipe-works-base design system ([bf663e6](https://github.com/pipe-works/pipeworks_mud_server/commit/bf663e656642fd4787a4973b642176b73f5f0340))
* **web:** migrate admin CSS to pipe-works-base design system ([d54a9b4](https://github.com/pipe-works/pipeworks_mud_server/commit/d54a9b4f9c9599fc9e6521b7ec6451ca370769e2))
* **world:** enable OOC→IC translation layer for pipeworks_web ([#137](https://github.com/pipe-works/pipeworks_mud_server/issues/137)) ([40e5d99](https://github.com/pipe-works/pipeworks_mud_server/commit/40e5d992bf4ae1330c2c6e1586007602b056b694))


### Bug Fixes

* **chat:** address six chat system gaps ([#134](https://github.com/pipe-works/pipeworks_mud_server/issues/134)) ([723a3e6](https://github.com/pipe-works/pipeworks_mud_server/commit/723a3e657ee0ededee86be9e9a3939c8ff0c67cd))

## [0.3.10](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.3.9...mud_server-v0.3.10) (2026-02-18)


### Features

* **db:** complete phase 4 typed errors and hot-path plan guards ([#119](https://github.com/pipe-works/pipeworks_mud_server/issues/119)) ([8f6b13c](https://github.com/pipe-works/pipeworks_mud_server/commit/8f6b13c1f599481d3154f6fc953e6c5910214026))
* **db:** drop create-user compat args and dead helpers ([2575dcf](https://github.com/pipe-works/pipeworks_mud_server/commit/2575dcfa1214a379001db8141fad30590695785f))
* **db:** enforce strict character identity resolution ([7786dbb](https://github.com/pipe-works/pipeworks_mud_server/commit/7786dbba6e4e842dcfbf3132019f82f96efdfefa))
* **db:** enforce strict character identity resolution ([9f272d3](https://github.com/pipe-works/pipeworks_mud_server/commit/9f272d35604ac9635bf2b3e3de2d7dd219273696))
* **db:** extract admin axis and events repositories ([7b2ec57](https://github.com/pipe-works/pipeworks_mud_server/commit/7b2ec57383909060a5327d59dd94ebd8ec78cae4))
* **db:** extract admin axis and events repositories ([ca7608d](https://github.com/pipe-works/pipeworks_mud_server/commit/ca7608dd7bcf4e4a0a996c5c84cd34cc220a2808))
* **db:** extract characters chat and worlds repositories ([8ea0ed6](https://github.com/pipe-works/pipeworks_mud_server/commit/8ea0ed6a9447089aa98a86520b94131f38d07c74))
* **db:** extract characters chat and worlds repositories ([bdfaac8](https://github.com/pipe-works/pipeworks_mud_server/commit/bdfaac8ae729fe797234de12dfb07f964ce4a8bb))
* **db:** extract connection and schema foundations ([0d5a2e5](https://github.com/pipe-works/pipeworks_mud_server/commit/0d5a2e5a87c849537ff0a8e3178d367dfdcb51b6))
* **db:** extract connection and schema foundations ([d4a9e51](https://github.com/pipe-works/pipeworks_mud_server/commit/d4a9e514ff46ed9ae1886fad9ddbc6fe6505e2ff))
* **db:** extract users and sessions repositories ([e0a9686](https://github.com/pipe-works/pipeworks_mud_server/commit/e0a9686a0d6e16bc4df554e084f446294a2f8745))
* **db:** extract users and sessions repositories ([414d51b](https://github.com/pipe-works/pipeworks_mud_server/commit/414d51be0dab37582145382122069213d6492427))
* **db:** harden facade with explicit public API contract ([b588583](https://github.com/pipe-works/pipeworks_mud_server/commit/b588583e8833afe02a5b12bda427ffb37e3941a4))
* **db:** harden facade with explicit public API contract ([7695373](https://github.com/pipe-works/pipeworks_mud_server/commit/7695373d8aba3244cfeb3dc0373fb5f97062f41e))
* **db:** phase 4 typed repository errors and API boundary mapping ([#118](https://github.com/pipe-works/pipeworks_mud_server/issues/118)) ([fdef70b](https://github.com/pipe-works/pipeworks_mud_server/commit/fdef70b33c664752e46caea240bcd30ae490cfde))
* **db:** remove account-create compat args and prune dead DB helpers ([919fb9d](https://github.com/pipe-works/pipeworks_mud_server/commit/919fb9da347399c551cad987fcf2ff26685e291b))
* **db:** remove legacy player shim API surface ([5fdc622](https://github.com/pipe-works/pipeworks_mud_server/commit/5fdc6223359be856d1f038c812776eaa8845d1c2))
* **db:** remove legacy player shim API surface ([d5c0475](https://github.com/pipe-works/pipeworks_mud_server/commit/d5c0475d7e1259ec5599321bf6692abbc3e10da9))
* **db:** require explicit world ids for character paths ([2abec9f](https://github.com/pipe-works/pipeworks_mud_server/commit/2abec9ff0ef34c2df0dd805488300397299d7b42))
* **db:** require explicit world ids for character paths ([6e353ed](https://github.com/pipe-works/pipeworks_mud_server/commit/6e353ed4212483ba5ff3cd6ee8984337bda6ef75))
* **db:** require explicit world ids for runtime state paths ([f9df116](https://github.com/pipe-works/pipeworks_mud_server/commit/f9df116b518f960fbd8728fea5f06ba10f696f6f))
* **db:** require explicit world ids for runtime state paths ([a9de263](https://github.com/pipe-works/pipeworks_mud_server/commit/a9de2634e4fae1b072d8b9b0dd3b53c8121c19ce))
* **db:** require explicit world scope for active character queries ([be6eeb0](https://github.com/pipe-works/pipeworks_mud_server/commit/be6eeb0d1131e7cbb5ef8c781f833fd501db1a0b))
* **db:** require explicit world scope for active character queries ([293999d](https://github.com/pipe-works/pipeworks_mud_server/commit/293999d345ab2167f731c447cf39287ca23f7690))
* **db:** stabilize facade import path and shared db types ([09fddb9](https://github.com/pipe-works/pipeworks_mud_server/commit/09fddb91642ee834190d45c4a140fc7af353eda2))
* **db:** stabilize facade imports and shared db types ([dd9661d](https://github.com/pipe-works/pipeworks_mud_server/commit/dd9661dd8062a7cb5fdfc67790f6bf8cc1179459))


### Bug Fixes

* **db:** forward facade monkeypatch writes to database module ([ba3d1ba](https://github.com/pipe-works/pipeworks_mud_server/commit/ba3d1ba2a932cd6aabbecfee792409744fb17a9f))
* **db:** preserve facade patch teardown semantics ([dec987e](https://github.com/pipe-works/pipeworks_mud_server/commit/dec987e8a6185fb1fe8afa42cca5cbf1c8f5cd39))
* **db:** re-export axis registry seed stats from compatibility module ([bc794ff](https://github.com/pipe-works/pipeworks_mud_server/commit/bc794ffe9f0154863bf490fa5e7e814f43441579))
* **db:** restore database import path for app entry points ([adf2193](https://github.com/pipe-works/pipeworks_mud_server/commit/adf219353c3e114c36179953a5787c3f76e21b3a))


### Documentation

* **db:** align refactor architecture and schema docs ([#131](https://github.com/pipe-works/pipeworks_mud_server/issues/131)) ([c13e5ba](https://github.com/pipe-works/pipeworks_mud_server/commit/c13e5baea53f52f4a72a9e639063bbd4e9ba3ccf))

## [0.3.9](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.3.8...mud_server-v0.3.9) (2026-02-16)


### Features

* **policy:** implement section 3 world access foundations ([001101c](https://github.com/pipe-works/pipeworks_mud_server/commit/001101c71caa9eddd3ba78a2db9be861444ef824))
* **policy:** implement section 3 world access foundations ([7b801f1](https://github.com/pipe-works/pipeworks_mud_server/commit/7b801f1998eb7a48b692443af217fa9e697e47b7))

## [0.3.8](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.3.7...mud_server-v0.3.8) (2026-02-16)


### Features

* **admin:** add section 2 account and character dashboards ([8470bd0](https://github.com/pipe-works/pipeworks_mud_server/commit/8470bd0274304c1b6475914ac05333dcfaa4fd25))
* **admin:** complete section 2 active users dashboards ([3699d39](https://github.com/pipe-works/pipeworks_mud_server/commit/3699d392537910360f8fade9c6c37dad0fc05ac6))
* **auth:** enforce account-only registration flow ([7acec29](https://github.com/pipe-works/pipeworks_mud_server/commit/7acec2944d2a2aab4398f12e2efb5b007ca6b1d0))
* **auth:** enforce account-only registration flow ([6825b6d](https://github.com/pipe-works/pipeworks_mud_server/commit/6825b6de48075e48c789b584b2cb64a3a43e2aaf))

## [0.3.7](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.3.6...mud_server-v0.3.7) (2026-02-16)


### Features

* **admin:** add character lifecycle controls ([e9f8125](https://github.com/pipe-works/pipeworks_mud_server/commit/e9f81254f78013a90807e6e50aaafc2dd515e809))
* **admin:** add character lifecycle controls ([8ebc909](https://github.com/pipe-works/pipeworks_mud_server/commit/8ebc909549711dc1df314144d3901894865cef92))
* **admin:** add world operations status and kick controls ([eb0cb2b](https://github.com/pipe-works/pipeworks_mud_server/commit/eb0cb2bae252b4ad32e29d933afc8eac56c7b579))
* **admin:** world operations status + kick controls ([ace07fb](https://github.com/pipe-works/pipeworks_mud_server/commit/ace07fb184380a146d5ed9c2fc8fa63bbc335c2e))
* **api:** include guest entity state in onboarding ([cc7780a](https://github.com/pipe-works/pipeworks_mud_server/commit/cc7780a38bcd97f24f541e22cd41ef0627f20bbd))
* **api:** include guest entity state in onboarding ([0ec1002](https://github.com/pipe-works/pipeworks_mud_server/commit/0ec10028d0f7ed5aba14de68d9691a928cc57deb))
* **core:** randomize snapshot seed and add occupation axes ([e904a6b](https://github.com/pipe-works/pipeworks_mud_server/commit/e904a6b2e8d5b4904960b74099539d599c7a8905))
* **core:** randomize snapshot seed and add occupation axes ([23f1e39](https://github.com/pipe-works/pipeworks_mud_server/commit/23f1e395b6bbcb754af7136859d8cdd227adf224))
* **db:** enforce account-first session selection model ([9c7f2d4](https://github.com/pipe-works/pipeworks_mud_server/commit/9c7f2d485836a92cc28428fd5715f0e190a635aa))
* **db:** enforce account-first session selection model ([a3868f8](https://github.com/pipe-works/pipeworks_mud_server/commit/a3868f89d4e5545f43c754f97a9dac786502e3e1))
* **db:** enforce session invariants with sqlite triggers ([dc0a521](https://github.com/pipe-works/pipeworks_mud_server/commit/dc0a521272040ad89916ad69c7786b150c6e78be))
* **db:** enforce sqlite session invariants ([afee4ef](https://github.com/pipe-works/pipeworks_mud_server/commit/afee4ef1e25286d6f6c1bc0f008bfbdb91ec1267))

## [0.3.6](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.3.5...mud_server-v0.3.6) (2026-02-15)


### Features

* **admin:** add users table filters ([e3d0b6c](https://github.com/pipe-works/pipeworks_mud_server/commit/e3d0b6c55425281f2cd89b2c06453991f460656d))
* **admin:** add users table filters ([1dddfb9](https://github.com/pipe-works/pipeworks_mud_server/commit/1dddfb997ea29c8bc2f5576c4013898f2ce98013))
* **admin:** expand axis inspector docs ([4040d53](https://github.com/pipe-works/pipeworks_mud_server/commit/4040d53347d56487eb87df2567e4807f57e9870d))
* **admin:** expand axis inspector docs ([ff2b817](https://github.com/pipe-works/pipeworks_mud_server/commit/ff2b8172e6f14aab46c341fd5200e87d2feefb0e))
* **admin:** expose axis state in user details ([#91](https://github.com/pipe-works/pipeworks_mud_server/issues/91)) ([636463c](https://github.com/pipe-works/pipeworks_mud_server/commit/636463cb20bd9c810f687e48bedd14bc9e93f228))
* **admin:** refine users layout ([03a7f9a](https://github.com/pipe-works/pipeworks_mud_server/commit/03a7f9a832bf0b6085c7d2e7d777200e07fd7373))
* **admin:** refine users layout ([d9f3ca5](https://github.com/pipe-works/pipeworks_mud_server/commit/d9f3ca5e39be744bab04ba4ceb5cd44e875e839f))
* **admin:** show online status and axis events ([d085703](https://github.com/pipe-works/pipeworks_mud_server/commit/d085703572418a6ed0450d5b89d0c8341d0d81f7))
* **admin:** show online status and axis events ([3266e9d](https://github.com/pipe-works/pipeworks_mud_server/commit/3266e9d3da7ab7cac25d9f41d69df9b13a1272c4))
* **core:** add axis policy foundations ([01f1d76](https://github.com/pipe-works/pipeworks_mud_server/commit/01f1d7656c6c988230634bcdcada7d2763176b43))
* **core:** add axis policy foundations ([f9750e5](https://github.com/pipe-works/pipeworks_mud_server/commit/f9750e58e7eebe126486617c6fb335bc4ca52ac2))
* **core:** apply axis events atomically ([#90](https://github.com/pipe-works/pipeworks_mud_server/issues/90)) ([7eccb21](https://github.com/pipe-works/pipeworks_mud_server/commit/7eccb21c02576dea15433ef9e91925f6d98dd8b2))
* **core:** seed axis registry at startup ([#88](https://github.com/pipe-works/pipeworks_mud_server/issues/88)) ([7c9f9aa](https://github.com/pipe-works/pipeworks_mud_server/commit/7c9f9aa3cff99195465134bb640d0522c5da35a5))
* **core:** seed character state snapshots ([#89](https://github.com/pipe-works/pipeworks_mud_server/issues/89)) ([fec82a5](https://github.com/pipe-works/pipeworks_mud_server/commit/fec82a5b1e5258cef7cb4293bd78708e29de733e))

## [0.3.5](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.3.4...mud_server-v0.3.5) (2026-02-14)


### Features

* **web:** add play shell scaffolding ([ee65ef7](https://github.com/pipe-works/pipeworks_mud_server/commit/ee65ef7abccd3f804e328618fd4e992e3d86c0c1))
* **web:** add play UI layout scaffold ([088b484](https://github.com/pipe-works/pipeworks_mud_server/commit/088b4845ca5b19b8e92ecd5a64abd406395538ba))
* **web:** add play UI shell ([6868746](https://github.com/pipe-works/pipeworks_mud_server/commit/6868746676da31a82bc6fecb67752bbd5f1c1414))
* **web:** scaffold play UI layout ([ba71d75](https://github.com/pipe-works/pipeworks_mud_server/commit/ba71d75ec4fad53da5fab3a614c05feb1b9472ac))
* **web:** simplify play login flow ([21dd729](https://github.com/pipe-works/pipeworks_mud_server/commit/21dd7295a1bdc7a4692c564d6691dd34f71c5baf))
* **web:** simplify play login flow ([883ff32](https://github.com/pipe-works/pipeworks_mud_server/commit/883ff32b1cc581d8b91fe892f896c14135ce28cc))


### Bug Fixes

* **web:** add play shell base styles ([a74dcb6](https://github.com/pipe-works/pipeworks_mud_server/commit/a74dcb69a14eeda4be15155326bc86fe065ff92f))
* **web:** style play shell states ([0e5eebb](https://github.com/pipe-works/pipeworks_mud_server/commit/0e5eebb3cce880b2566464602744ac39b1354606))


### Documentation

* **web:** add play web UI guide ([22a07d7](https://github.com/pipe-works/pipeworks_mud_server/commit/22a07d76f4a74ca11b06ab6ed8827d1d2ee870e8))
* **web:** add play web UI guide ([5c5b0cc](https://github.com/pipe-works/pipeworks_mud_server/commit/5c5b0ccb2fa8913009c4021b5342db7cc89b841e))

## [0.3.4](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.3.3...mud_server-v0.3.4) (2026-02-14)


### Features

* **web:** add admin data pages ([70a39dd](https://github.com/pipe-works/pipeworks_mud_server/commit/70a39dd414780d4150f7671411938a5de3cbdea6))
* **web:** add admin data pages ([77648a1](https://github.com/pipe-works/pipeworks_mud_server/commit/77648a1df04cf27c88c989184154e4f028ea900f))
* **web:** add admin webui scaffolding ([ed3070d](https://github.com/pipe-works/pipeworks_mud_server/commit/ed3070d410ab7bc6b610652df759c898c09c2a87))
* **web:** add admin webui scaffolding ([2074348](https://github.com/pipe-works/pipeworks_mud_server/commit/2074348536d2d12daea1df46a380fcc58f0f6514))
* **web:** add dashboard layout and routing ([b9e62b9](https://github.com/pipe-works/pipeworks_mud_server/commit/b9e62b954f4978cb9eb75ee89a432b15de8e66e4))
* **web:** add dashboard layout and routing ([395ad38](https://github.com/pipe-works/pipeworks_mud_server/commit/395ad38731363f805796e400e7cc0525c7150ab6))
* **web:** add login flow scaffolding ([8bced0e](https://github.com/pipe-works/pipeworks_mud_server/commit/8bced0edcce8bf8df487bf845bfe788c7e2a8c7f))
* **web:** add login flow scaffolding ([cc3e545](https://github.com/pipe-works/pipeworks_mud_server/commit/cc3e5451c7f174fd0a3cf96bd5e1914c04249562))
* **web:** add schema view and retire gradio ([#76](https://github.com/pipe-works/pipeworks_mud_server/issues/76)) ([7189cd3](https://github.com/pipe-works/pipeworks_mud_server/commit/7189cd31621f2e10aa553967e11bceb262366f4a))
* **web:** refresh admin dashboard layout ([#75](https://github.com/pipe-works/pipeworks_mud_server/issues/75)) ([5e96fbc](https://github.com/pipe-works/pipeworks_mud_server/commit/5e96fbcf8cd87c7adc6693ca8cca957c6ff18c03))


### Documentation

* **security:** add admin mTLS guide ([48f9a6f](https://github.com/pipe-works/pipeworks_mud_server/commit/48f9a6f67df56656ad953cc19c8c3afef3c914ed))
* **security:** add admin mTLS guide ([3a8c5b4](https://github.com/pipe-works/pipeworks_mud_server/commit/3a8c5b42974e3c458cd8934dfbf35e61802892a8))
* **web:** replace gradio references ([72610cf](https://github.com/pipe-works/pipeworks_mud_server/commit/72610cf4a6287f2fbed6cc44b9cde4aa4edb2b03))
* **web:** replace gradio references ([afc86a6](https://github.com/pipe-works/pipeworks_mud_server/commit/afc86a6411e652162476ff8f51491ed191bfb88c))

## [0.3.3](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.3.2...mud_server-v0.3.3) (2026-02-13)


### Documentation

* **api:** note register_routes import path change ([c46c5b8](https://github.com/pipe-works/pipeworks_mud_server/commit/c46c5b8853f4227fb8ae97188213ba7fd97952ca))
* **api:** note register_routes import path change ([2efe672](https://github.com/pipe-works/pipeworks_mud_server/commit/2efe67242a600fe3edd3dab889e7f4d6b2c59b39))

## [0.3.2](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.3.1...mud_server-v0.3.2) (2026-02-13)


### Features

* **admin_tui:** add user and character dashboards ([50ade69](https://github.com/pipe-works/pipeworks_mud_server/commit/50ade690fd33414f3a4d3d4f8c298e13ff029855))
* **admin_tui:** add user and character dashboards ([f35f639](https://github.com/pipe-works/pipeworks_mud_server/commit/f35f639ed52695e792ab2adfc984b710ad40bde0))
* **admin_tui:** add worlds tab and harden world loader ([a5ebcca](https://github.com/pipe-works/pipeworks_mud_server/commit/a5ebcca5bfa1ab36b3737125d68b2a7cc932eae2))
* **admin-tui:** stabilize table selection ([dcacaaf](https://github.com/pipe-works/pipeworks_mud_server/commit/dcacaaf174f015b5378cdfb550b4ec8fbdae3ca6))
* **admin-tui:** stabilize table selection ([df04e88](https://github.com/pipe-works/pipeworks_mud_server/commit/df04e88c5d127588922cf8010e822d064511cfd5))
* **api:** add register-guest endpoint ([923e0a0](https://github.com/pipe-works/pipeworks_mud_server/commit/923e0a07666fa4ba71cb613e051be90ab824a0bf))
* **api:** add register-guest endpoint ([c4286d4](https://github.com/pipe-works/pipeworks_mud_server/commit/c4286d4c94db2da3837d9297f380a2c183095a49))
* **cli:** add init-db migrate option ([6ece6b4](https://github.com/pipe-works/pipeworks_mud_server/commit/6ece6b4b76a93eade330fdff931aa65c37277232))
* **core:** use world registry in engine ([baa32c0](https://github.com/pipe-works/pipeworks_mud_server/commit/baa32c0401452d7adb2a39419f2f1a49167424d6))
* **data:** add multi-world data layout ([e945e67](https://github.com/pipe-works/pipeworks_mud_server/commit/e945e67db0e622970f2fa6071a7398ee7e24cca6))
* **multiworld:** add world scoping and auth flow ([1450880](https://github.com/pipe-works/pipeworks_mud_server/commit/1450880007ca88a598dac2e7a507010cd990b997))
* **multiworld:** add world scoping and auth flow ([e087254](https://github.com/pipe-works/pipeworks_mud_server/commit/e0872544d4a63a4a47ab5601d41d4d84bc5f0eaf))


### Bug Fixes

* **admin_tui:** align users table ([1cae99a](https://github.com/pipe-works/pipeworks_mud_server/commit/1cae99a5f63c2824ada0876364f9e6f3e0d4d8ab))
* **admin_tui:** align users table ([60c1fc3](https://github.com/pipe-works/pipeworks_mud_server/commit/60c1fc32322f74bec03055a45b0f38bad2b5447a))
* **admin_tui:** improve navigation and character naming ([31f7d57](https://github.com/pipe-works/pipeworks_mud_server/commit/31f7d573647d2efa148982fb9c6c27721ea58f31))
* **admin_tui:** open user detail and avoid cursor crashes ([969c77b](https://github.com/pipe-works/pipeworks_mud_server/commit/969c77ba6425fa5c71946e6447b8cba54eb9ba6f))
* **admin_tui:** selection and cursor navigation ([302a7aa](https://github.com/pipe-works/pipeworks_mud_server/commit/302a7aa98799b622d5f438b28326b49f5c9c40e8))
* **chat:** resolve usernames to characters ([06fd374](https://github.com/pipe-works/pipeworks_mud_server/commit/06fd3745c63757c2d4814319219d2792b0cb5748))
* **db:** map usernames to default characters ([d14bccb](https://github.com/pipe-works/pipeworks_mud_server/commit/d14bccbe86cbe1c5101f624565b81d9fd45f535f))
* **test:** avoid fixture call and guard migrate arg ([4fdf1cf](https://github.com/pipe-works/pipeworks_mud_server/commit/4fdf1cfc5fda5a524318bafdd1de788c501c7052))


### Documentation

* **api:** add register guest examples ([008cb3e](https://github.com/pipe-works/pipeworks_mud_server/commit/008cb3e3b3350accf9f1d46de3e6f2b00c1ad810))
* **api:** add register guest examples ([fe06426](https://github.com/pipe-works/pipeworks_mud_server/commit/fe06426fa5cfe13714114f7ca21874af295ec1a7))
* **db:** update schema and bootstrap notes ([f87277d](https://github.com/pipe-works/pipeworks_mud_server/commit/f87277d70e5b5e714b05ac6d6782094f00217591))
* **db:** update schema and bootstrap notes ([d6c22cd](https://github.com/pipe-works/pipeworks_mud_server/commit/d6c22cd37d22af063e3ee2c4272bf95a186fc16d))
* update schema notes and add static dir ([368a123](https://github.com/pipe-works/pipeworks_mud_server/commit/368a123aa156371a41b1ad39ac88215583241952))

## [0.3.1](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.3.0...mud_server-v0.3.1) (2026-02-11)


### Features

* **db:** introduce users and characters schema ([afecf6c](https://github.com/pipe-works/pipeworks_mud_server/commit/afecf6cc3b4d05706d4d09a58620fa6e2b3cc855))
* **db:** introduce users and characters schema ([8b728cc](https://github.com/pipe-works/pipeworks_mud_server/commit/8b728cc19d2b393a8abf02c648ebcd9ff01f6079))


### Bug Fixes

* **db:** align tests with user/character schema ([a93669b](https://github.com/pipe-works/pipeworks_mud_server/commit/a93669bf3715246a8008b4817e39bc055fe19af0))

## [0.3.0](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.2.10...mud_server-v0.3.0) (2026-02-10)


### ⚠ BREAKING CHANGES

* **auth:** sessions are now database-backed with TTL + sliding expiration; session config keys have changed (ttl_minutes, sliding_expiration, allow_multiple_sessions).

### Features

* **admin-tui:** add admin user creation ([dbac2e5](https://github.com/pipe-works/pipeworks_mud_server/commit/dbac2e5022520405d592ba015894cb6045381d27))
* **admin-tui:** add admin user creation ([099b5b8](https://github.com/pipe-works/pipeworks_mud_server/commit/099b5b8f54b6234ac2b064c81c1bc48adf79cacd))
* **admin:** add client type to sessions ([33f64e3](https://github.com/pipe-works/pipeworks_mud_server/commit/33f64e3a7ff290ca391ecde6d6830bb557f198a8))
* **admin:** add user removal tools ([43e9545](https://github.com/pipe-works/pipeworks_mud_server/commit/43e9545ebb982e8302b3cf2921dcb2a081d42827))
* **admin:** add user removal tools ([0d1693d](https://github.com/pipe-works/pipeworks_mud_server/commit/0d1693d19db573e6f8d826f7389056d62b53e9a4))
* **auth:** add temporary visitor accounts ([bdb509d](https://github.com/pipe-works/pipeworks_mud_server/commit/bdb509d672a93bf2c53bdc22f778a8c6467c7f28))
* **auth:** add temporary visitor accounts ([621d7ab](https://github.com/pipe-works/pipeworks_mud_server/commit/621d7abdb0f1a5d70640696d4df492f320bf77b8))
* **auth:** move sessions to db-backed ttl with sliding expiration ([671f037](https://github.com/pipe-works/pipeworks_mud_server/commit/671f03796e836519f8761562e4e12e7a5632200f))
* **tui:** add configurable keybindings ([41b026e](https://github.com/pipe-works/pipeworks_mud_server/commit/41b026e2b6c30440abf2776f211b16c46c841dde))
* **tui:** add configurable keybindings ([403c2a1](https://github.com/pipe-works/pipeworks_mud_server/commit/403c2a180814a2d3c0ce81917b7098b004227e80))
* **tui:** add database table browser ([9aa9f07](https://github.com/pipe-works/pipeworks_mud_server/commit/9aa9f075f287f98ba60c9716a422566852e388b8))
* **tui:** add database table browser ([87a3b47](https://github.com/pipe-works/pipeworks_mud_server/commit/87a3b47bcb9bb7cc0a6f9b8f39f921f50b32103e))


### Bug Fixes

* **db:** update last_login on session creation ([36e915d](https://github.com/pipe-works/pipeworks_mud_server/commit/36e915df51362231efb13cd45653af4630d25327))
* **tests:** align client header expectations ([4c53e96](https://github.com/pipe-works/pipeworks_mud_server/commit/4c53e9672a7498dc6a9d9f8b09e761e67a0992e0))
* **tui:** ensure database tables expand to fill tab ([b36c092](https://github.com/pipe-works/pipeworks_mud_server/commit/b36c092eb12df8e919398ba3d9178c1efc415af9))
* **tui:** pass session_id as query param for db views ([acdbd76](https://github.com/pipe-works/pipeworks_mud_server/commit/acdbd765e02afb6a033e862372eda41ceb687aba))
* **tui:** pass session_id as query param for db views ([f93d895](https://github.com/pipe-works/pipeworks_mud_server/commit/f93d895139037d65e1388c593551e053a43e2d80))

## [0.2.10](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.2.9...mud_server-v0.2.10) (2026-02-01)


### Bug Fixes

* **data:** rename upper_landing to dark_passage ([#41](https://github.com/pipe-works/pipeworks_mud_server/issues/41)) ([d567f50](https://github.com/pipe-works/pipeworks_mud_server/commit/d567f5074a8d6c54c9610c923cc2d8512b083b4f))

## [0.2.9](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.2.8...mud_server-v0.2.9) (2026-02-01)


### Features

* **core:** implement zone-based world architecture ([#38](https://github.com/pipe-works/pipeworks_mud_server/issues/38)) ([deac289](https://github.com/pipe-works/pipeworks_mud_server/commit/deac289013ab5f896316c03021b62b1683ae30f5))

## [0.2.8](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.2.7...mud_server-v0.2.8) (2026-01-31)


### Features

* **core:** add up/down movement commands and pub crawl world data ([3c64630](https://github.com/pipe-works/pipeworks_mud_server/commit/3c64630daca66367f33469150910a956c8c736a2))
* **core:** add up/down movement commands and pub crawl world data ([28e3ac4](https://github.com/pipe-works/pipeworks_mud_server/commit/28e3ac4fb0599c43b51487766ab99774446daba6))


### Bug Fixes

* **examples:** improve ASCII map alignment and add box templates ([#35](https://github.com/pipe-works/pipeworks_mud_server/issues/35)) ([5ed2950](https://github.com/pipe-works/pipeworks_mud_server/commit/5ed29508dd8a3c5ea53e979c1e260226c2d8c4ba))
* **tests:** update opposite_direction test for up/down support ([0acb79f](https://github.com/pipe-works/pipeworks_mud_server/commit/0acb79f6754ff0f4a353794e9b8ba8d2427c4e8d))

## [0.2.7](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.2.6...mud_server-v0.2.7) (2026-01-31)


### Features

* **core:** add event bus infrastructure for plugin system ([#31](https://github.com/pipe-works/pipeworks_mud_server/issues/31)) ([64b5282](https://github.com/pipe-works/pipeworks_mud_server/commit/64b52820678f9563cef8374eab4e68669f09df52))
* **examples:** add ASCII movement demo for REST API ([#33](https://github.com/pipe-works/pipeworks_mud_server/issues/33)) ([1645dcb](https://github.com/pipe-works/pipeworks_mud_server/commit/1645dcbae09fc8f9f6c6754cfc2918d1be656e4d))

## [0.2.6](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.2.5...mud_server-v0.2.6) (2026-01-31)


### Bug Fixes

* **security:** add timing attack prevention and XSS sanitization ([#29](https://github.com/pipe-works/pipeworks_mud_server/issues/29)) ([b52b91a](https://github.com/pipe-works/pipeworks_mud_server/commit/b52b91aba519e42918bc93c3dc9670509c57095e))

## [0.2.5](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.2.4...mud_server-v0.2.5) (2026-01-31)


### Features

* **security:** add config system for CORS and server settings ([#27](https://github.com/pipe-works/pipeworks_mud_server/issues/27)) ([6fe4680](https://github.com/pipe-works/pipeworks_mud_server/commit/6fe468069b07efe9b6cb8d9cf6b00b97c5631b83))

## [0.2.4](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.2.3...mud_server-v0.2.4) (2026-01-30)


### Features

* **admin_tui:** add database viewer screen for superusers ([#25](https://github.com/pipe-works/pipeworks_mud_server/issues/25)) ([872b4d5](https://github.com/pipe-works/pipeworks_mud_server/commit/872b4d5e12233a44e3b4f24ce1784d270068615e))

## [0.2.3](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.2.2...mud_server-v0.2.3) (2026-01-30)


### Features

* **admin:** add Textual TUI and reorganize admin interfaces ([#20](https://github.com/pipe-works/pipeworks_mud_server/issues/20)) ([75e6dae](https://github.com/pipe-works/pipeworks_mud_server/commit/75e6dae91bec4fecafe6fd0e8d4a609e444dd037))


### Bug Fixes

* **admin_tui:** improve error handling for server responses and dashboard ([#23](https://github.com/pipe-works/pipeworks_mud_server/issues/23)) ([67bcc8b](https://github.com/pipe-works/pipeworks_mud_server/commit/67bcc8b3bef5d6ac6ad4ba6e5bdfd17b6f025c06))
* **admin_tui:** resolve TUI freeze and session management issues ([#24](https://github.com/pipe-works/pipeworks_mud_server/issues/24)) ([5ea542f](https://github.com/pipe-works/pipeworks_mud_server/commit/5ea542f5e68404f4a7d1d2c785189a5b879cc48d))


### Documentation

* add Admin TUI documentation to getting started guide ([#22](https://github.com/pipe-works/pipeworks_mud_server/issues/22)) ([96eab20](https://github.com/pipe-works/pipeworks_mud_server/commit/96eab20a63b35c80c49427e74e9df54f8d42033f))

## [0.2.2](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.2.1...mud_server-v0.2.2) (2026-01-30)


### Features

* **cli:** add port auto-discovery for API server and UI client ([#18](https://github.com/pipe-works/pipeworks_mud_server/issues/18)) ([b31d8d1](https://github.com/pipe-works/pipeworks_mud_server/commit/b31d8d1cd322d4f26c0c201a585b823c34e9c7ea))
* **security:** implement comprehensive NIST-aligned password policy ([#19](https://github.com/pipe-works/pipeworks_mud_server/issues/19)) ([2909143](https://github.com/pipe-works/pipeworks_mud_server/commit/2909143131a6ce46d84d6a5fe1879ac068b34bab))


### Bug Fixes

* **deps:** downgrade bcrypt to 3.2.2 for passlib compatibility ([#16](https://github.com/pipe-works/pipeworks_mud_server/issues/16)) ([22d1dca](https://github.com/pipe-works/pipeworks_mud_server/commit/22d1dca1182e7832ddbb5a572a59a07290436332))

## [0.2.1](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.2.0...mud_server-v0.2.1) (2026-01-30)


### Documentation

* align ReadTheDocs with pipe-works organization standards ([#14](https://github.com/pipe-works/pipeworks_mud_server/issues/14)) ([8306b70](https://github.com/pipe-works/pipeworks_mud_server/commit/8306b703e4686cf2108f18e0fbdea1fa271e32b1))

## [0.2.0](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.1.2...mud_server-v0.2.0) (2026-01-30)


### ⚠ BREAKING CHANGES

* No default admin user created on init. Use CLI or env vars.

### Features

* add CLI with secure superuser management ([#11](https://github.com/pipe-works/pipeworks_mud_server/issues/11)) ([a5f7321](https://github.com/pipe-works/pipeworks_mud_server/commit/a5f732197500c727b362bf28a5831bfe303e8d32))


### Bug Fixes

* **security:** upgrade python-multipart to 0.0.22 ([#12](https://github.com/pipe-works/pipeworks_mud_server/issues/12)) ([08d1eeb](https://github.com/pipe-works/pipeworks_mud_server/commit/08d1eeb3b4b26664aa09867bb2c39156b1dd7e9d))


### Documentation

* add pipe-works organization standards reference to CLAUDE.md ([#13](https://github.com/pipe-works/pipeworks_mud_server/issues/13)) ([853acb7](https://github.com/pipe-works/pipeworks_mud_server/commit/853acb7ce0f906bfbd4490129796b9f0224aa8b5))
* rebrand as generic PipeWorks MUD Server framework ([#9](https://github.com/pipe-works/pipeworks_mud_server/issues/9)) ([f058b5d](https://github.com/pipe-works/pipeworks_mud_server/commit/f058b5d45046b1751e126d664d7754716322b3c3))

## [0.1.2](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.1.1...mud_server-v0.1.2) (2026-01-27)


### Bug Fixes

* **packaging:** exclude __pycache__ from distribution ([#7](https://github.com/pipe-works/pipeworks_mud_server/issues/7)) ([1048c66](https://github.com/pipe-works/pipeworks_mud_server/commit/1048c6653aad4e3ba935e46f74267b6f2c0bbfa7))

## [0.1.1](https://github.com/pipe-works/pipeworks_mud_server/compare/mud_server-v0.1.0...mud_server-v0.1.1) (2026-01-26)


### Features

* Adopt organization-wide standards and reusable CI workflow ([d378281](https://github.com/pipe-works/pipeworks_mud_server/commit/d378281eeca8c81fda91be1f04021dbd5116c257))
* **ci:** add release automation workflows ([#4](https://github.com/pipe-works/pipeworks_mud_server/issues/4)) ([4281641](https://github.com/pipe-works/pipeworks_mud_server/commit/428164110b83cd5f845e0e778f7945ac15b6fb74))
* **ci:** add workflow_dispatch trigger to release-please ([bbb646a](https://github.com/pipe-works/pipeworks_mud_server/commit/bbb646ad8c27c8dc5e1d32b66fa79cf8fc6961a1))
* Enable MkDocs documentation builds in CI ([a7e75ca](https://github.com/pipe-works/pipeworks_mud_server/commit/a7e75ca16a3bc016e471c80c8c2828d2b974d509))
* Upgrade to enhanced organization pre-commit standards ([fde93e8](https://github.com/pipe-works/pipeworks_mud_server/commit/fde93e8e25f3a853c37a916f00159aef86141252))


### Bug Fixes

* Add missing XML coverage report for Codecov upload ([5c89968](https://github.com/pipe-works/pipeworks_mud_server/commit/5c89968b5629fcbbef1e9e9865c86488735d33a5))
* **ci:** add required permissions to release-please workflow ([f46dfb0](https://github.com/pipe-works/pipeworks_mud_server/commit/f46dfb03fdf8bc277a8c82c2162ff5ff05c0074f))
* **ci:** add security-events permission for CodeQL ([51ca13b](https://github.com/pipe-works/pipeworks_mud_server/commit/51ca13b3cdf23f9a1e697df4d4d23d7abc15bbe8))
* Exclude UI code from coverage to fix failing CI ([22b8c9d](https://github.com/pipe-works/pipeworks_mud_server/commit/22b8c9dbc186b068592a1592ddb38c1b5db593c8))
* **pre-commit:** correct hook execution order ([8de65a3](https://github.com/pipe-works/pipeworks_mud_server/commit/8de65a34c891117152ca868e43506b5c423f259b))
