# Changelog

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
