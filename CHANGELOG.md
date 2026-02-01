# Changelog

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
