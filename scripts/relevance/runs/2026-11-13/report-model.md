# T27 relevance report

Snapshot `8a7733149acd97e2ed2b736a2001516b5ab33ba809b6a37d33ecc14c5d6aece0`; judge: model (Claude, blind).
Versions: archive_as_of=None, archive_repositories=204, collected_at=2026-11-13T11:59:41+00:00, collection=repo_chunks_e5small_v1, commit=0b27f243017253d93aa10313bd09bd9de9ce3f30, ideas_sha256=c7bf3d1784a9cdb2bf4757116808cdd5a346ae6ac7bb5483bfd33b5695e1a3d9, keyword_candidates=100, model_revision=614241f622f53c4eeff9890bdc4f31cfecc418b3, ranking=rrf-v1, rrf_k=60, warmup={'archive_status': 'failed', 'attempts': 3}

Judged pool: the union of each run's top 10 results per idea, judged blind (0 not useful, 1 partly, 2 good match). Recall@20 is judged-pool recall, not recall over all of GitHub. Unjudged results count as not relevant. Ideas with any unjudged pooled result are left out.

Complete ideas: 58 of 58. Ideas with nothing relevant: 12. Labels marked unsure: 164.

Ideas searched again after an archive failure: 2; archive still failed after retries: 1.

| Run | Mean nDCG@10 | Mean judged-pool Recall@20 | Ideas scored |
| --- | --- | --- | --- |
| Keyword (today) | 0.709 | 0.975 | 46 |
| Archive only | 0.023 | 0.025 | 46 |
| Hybrid | 0.429 | 1.000 | 46 |

## nDCG@10 by category

| Category | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| common | 0.740 | 0.010 | 0.475 |
| language | 0.675 | 0.041 | 0.427 |
| non_english | 0.585 | 0.098 | 0.277 |
| rare | 0.785 | 0.000 | 0.433 |
| vague | 0.497 | 0.000 | 0.320 |

## Where hybrid's relevant top-10 results came from

Both sources: 0; keyword only: 115; archive only: 6.

## Latency (ms)

Keyword source: median 3764, p95 4738. Hybrid: median 3771, p95 5068.

## Failure cases (hybrid nDCG@10 more than 0.1 below keyword)

- c02-markdown-notes: keyword 0.899, hybrid 0.573
- c05-chat-server: keyword 0.459, hybrid 0.000
- c06-password-manager: keyword 0.522, hybrid 0.118
- c07-url-shortener: keyword 0.676, hybrid 0.253
- c08-recipe: keyword 0.734, hybrid 0.360
- c09-habit: keyword 0.850, hybrid 0.596
- c10-pdf-tools: keyword 0.846, hybrid 0.383
- c12-home-dashboard: keyword 0.450, hybrid 0.086
- c13-uptime: keyword 0.661, hybrid 0.256
- c14-invoice: keyword 0.850, hybrid 0.731
- c15-photo-gallery: keyword 0.982, hybrid 0.781
- c16-music-player: keyword 0.662, hybrid 0.325
- c17-rss: keyword 0.987, hybrid 0.774
- c18-chatbot-docs: keyword 0.653, hybrid 0.387
- r01-beekeeping: keyword 0.873, hybrid 0.294
- r03-midi-sequencer: keyword 0.971, hybrid 0.593
- r04-ham-radio: keyword 0.578, hybrid 0.233
- r05-knitting: keyword 0.848, hybrid 0.398
- r06-astronomy: keyword 0.457, hybrid 0.167
- r07-plant-watering: keyword 0.973, hybrid 0.783
- r08-bird-sound: keyword 0.551, hybrid 0.174
- r09-genealogy: keyword 0.946, hybrid 0.570
- r11-tide: keyword 0.650, hybrid 0.195
- l02-go-reverse-proxy: keyword 0.622, hybrid 0.290
- l03-flutter-expense: keyword 0.865, hybrid 0.399
- l04-react-kanban: keyword 0.525, hybrid 0.252
- l05-python-scraper: keyword 0.694, hybrid 0.321
- l07-kotlin-reader: keyword 0.971, hybrid 0.592
- l08-typescript-orm: keyword 0.573, hybrid 0.417
- l09-cpp-game-engine: keyword 0.629, hybrid 0.440
- l10-elixir-realtime: keyword 0.746, hybrid 0.296
- l11-bash-dotfiles: keyword 0.634, hybrid 0.447
- l12-wasm-image: keyword 0.504, hybrid 0.328
- n02-es-recetas: keyword 0.561, hybrid 0.108
- n04-pt-financas: keyword 0.511, hybrid 0.098
- n05-ja-kakeibo: keyword 0.613, hybrid 0.264
- v02-vague-learn: keyword 0.564, hybrid 0.307

## Side by side

### c01-budget (common)

> a small app that tracks my monthly budget and spending

nDCG@10: Keyword (today) 0.579, Archive only 0.000, Hybrid 0.579
Status: Keyword (today) ok, Archive only failed, Hybrid degraded

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | steipete/CodexBar [0] |  | steipete/CodexBar [0] |
| 2 | nikilster/clawflows [0] |  | nikilster/clawflows [0] |
| 3 | dtyq/magic [0] |  | dtyq/magic [0] |
| 4 | layground/pockaw [2] |  | layground/pockaw [2] |
| 5 | lossless-protocols-org/zero [2] |  | lossless-protocols-org/zero [2] |
| 6 | awesome-selfhosted/awesome-selfhosted [1] |  | awesome-selfhosted/awesome-selfhosted [1] |
| 7 | kenlasko/monize [2] |  | kenlasko/monize [2] |
| 8 | tensorchord/Awesome-LLMOps [0] |  | tensorchord/Awesome-LLMOps [0] |
| 9 | QuesmaOrg/awesome-ai-tokenomics [0] |  | QuesmaOrg/awesome-ai-tokenomics [0] |
| 10 | ali-ahnaf/pocket_pixel [2] |  | ali-ahnaf/pocket_pixel [2] |

### c02-markdown-notes (common)

> an offline note taking app that stores notes as markdown files

nDCG@10: Keyword (today) 0.899, Archive only 0.000, Hybrid 0.573
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | Laverna/laverna [2] | Joohansson/keytools [0] | Laverna/laverna [2] |
| 2 | timothepoznanski/Poznote [1] | kawmra/Owl-Timekeeper [0] | Joohansson/keytools [0] |
| 3 | jaywcjlove/awesome-mac [1] | GalaxiMaster/wordini [0] | kawmra/Owl-Timekeeper [0] |
| 4 | Dhravya/notty [1] | qepting91/streamlitransomware [0] | timothepoznanski/Poznote [1] |
| 5 | Notely-Voice/NotelyVoice [0] | ciphergoth/pylambdac [0] | jaywcjlove/awesome-mac [1] |
| 6 | encryptic-team/encryptic [1] | Fernando-Sousa-Leal/github-slideshow [0] | GalaxiMaster/wordini [0] |
| 7 | mundimark/awesome-markdown-editors [1] | kirtanasingh/AttendanceManagementSystem [0] | qepting91/streamlitransomware [0] |
| 8 | inventory69/simple-notes-sync [2] | eyecatchup/MyCountdown-app [0] | Dhravya/notty [1] |
| 9 | pazguille/offline-first [0] | gugod/sitebrew [0] | ciphergoth/pylambdac [0] |
| 10 | cpbotha/nvpy [1] | ab-prog1/ab-prog1 [0] | Notely-Voice/NotelyVoice [0] |

### c03-todo-sync (common)

> a todo list that syncs between my phone and laptop

nDCG@10: Keyword (today) 1.000, Archive only 0.000, Hybrid 1.000
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | talex5/cuekeeper [1] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | talex5/cuekeeper [1] |
| 2 | lissy93/awesome-privacy [0] | BookingSync/bookingsync-api [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |
| 3 | nhadaututtheky/neural-memory [0] | Cyborgscode/Personal-Voice-Assistent [0] | BookingSync/bookingsync-api [0] |
| 4 | Runfusion/Fusion [0] | thinger-io/IOTMP-Arduino [0] | lissy93/awesome-privacy [0] |
| 5 | jaywcjlove/awesome-mac [0] | Joohansson/keytools [0] | Cyborgscode/Personal-Voice-Assistent [0] |
| 6 | serhii-londar/open-source-mac-os-apps [0] | nycynik/dotFiles [0] | nhadaututtheky/neural-memory [0] |
| 7 | NIT-Hamirpur-NITH/tipsNtricks [0] | antonkesy/tap-heading-unity [0] | thinger-io/IOTMP-Arduino [0] |
| 8 | ratatui/awesome-ratatui [0] | lcy-seso/lcy-seso.github.io [0] | Runfusion/Fusion [0] |
| 9 | OpenCoworkAI/open-codesign [0] | MuhammedOzby/network-examples [0] | jaywcjlove/awesome-mac [0] |
| 10 | auctors/free-lunch [0] | genesistoxical/crystal-folders [0] | Joohansson/keytools [0] |

### c04-static-blog (common)

> generate a static blog website from markdown posts

nDCG@10: Keyword (today) 0.585, Archive only 0.183, Hybrid 0.488
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | asyncapi/website [0] | gugod/sitebrew [1] | gugod/sitebrew [1] |
| 2 | jekyll/jekyll [2] | JRZhang2003/JRZhang2003.github.io [0] | asyncapi/website [0] |
| 3 | mono/website [0] | mathsgod/markdown-splitter [0] | jekyll/jekyll [2] |
| 4 | react/react-native-website [0] | SamSaffron/blog [0] | JRZhang2003/JRZhang2003.github.io [0] |
| 5 | HugoBlox/kit [2] | navjeetsingh/gatsby-blog [1] | mono/website [0] |
| 6 | timlrx/tailwind-nextjs-starter-blog [2] | ab-prog1/ab-prog1 [0] | mathsgod/markdown-splitter [0] |
| 7 | cake-build/website [0] | ondras/wwwsqldesigner [0] | SamSaffron/blog [0] |
| 8 | electron/website [0] | contributte/sentry [0] | react/react-native-website [0] |
| 9 | pycoder2000/blog [1] | contributte/cache [0] | HugoBlox/kit [2] |
| 10 | BabylonJS/Website [0] | Fernando-Sousa-Leal/github-slideshow [0] | navjeetsingh/gatsby-blog [1] |

### c05-chat-server (common)

> self-hosted team chat like a lightweight slack alternative

nDCG@10: Keyword (today) 0.459, Archive only 0.000, Hybrid 0.000
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | onyx-dot-app/onyx [0] | Cyborgscode/Personal-Voice-Assistent [0] | Cyborgscode/Personal-Voice-Assistent [0] |
| 2 | pluja/awesome-privacy [0] | ondras/wwwsqldesigner [0] | onyx-dot-app/onyx [0] |
| 3 | windmill-labs/windmill [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | ondras/wwwsqldesigner [0] |
| 4 | wmariuss/awesome-devops [0] | lucasdiedrich/node-freeipa [0] | pluja/awesome-privacy [0] |
| 5 | tortuvshin/open-apps [0] | DFE-Digital/support-for-social-workers [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |
| 6 | Anil-matcha/awesome-open-source-saas-alternatives [1] | ChivenZhang/OpenUI [0] | windmill-labs/windmill [0] |
| 7 | Atarity/deploy-your-own-saas [1] | theabbie/Doodle-Board [0] | lucasdiedrich/node-freeipa [0] |
| 8 | Erudika/scoold [0] | arif-js/datalogz-custom-tree-select [0] | wmariuss/awesome-devops [0] |
| 9 | ripienaar/free-for-dev [0] | SamSaffron/blog [0] | tortuvshin/open-apps [0] |
| 10 | macro-inc/macro [1] | eyecatchup/MyCountdown-app [0] | DFE-Digital/support-for-social-workers [0] |

### c06-password-manager (common)

> an open source password manager with browser extension

nDCG@10: Keyword (today) 0.522, Archive only 0.000, Hybrid 0.118
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | dkhamsing/open-source-ios-apps [0] | CaselIT/hash-set-map [0] | dkhamsing/open-source-ios-apps [0] |
| 2 | serhii-londar/open-source-mac-os-apps [0] | Joohansson/keytools [0] | CaselIT/hash-set-map [0] |
| 3 | jaywcjlove/awesome-mac [0] | alanta/EasyAuthDevProxy [0] | serhii-londar/open-source-mac-os-apps [0] |
| 4 | prasathmani/tinyfilemanager [0] | Cyborgscode/Personal-Voice-Assistent [0] | Joohansson/keytools [0] |
| 5 | passbolt/passbolt_browser_extension [2] | bills-appworks/bsky-sh-cli [0] | jaywcjlove/awesome-mac [0] |
| 6 | quoid/userscripts [0] | GridGain-Demos/spring-data-training [0] | alanta/EasyAuthDevProxy [0] |
| 7 | padloc/padloc [2] | Fernando-Sousa-Leal/github-slideshow [0] | prasathmani/tinyfilemanager [0] |
| 8 | passbolt/passbolt_api [2] | salrashid123/golang-jwt-pqc [0] | Cyborgscode/Personal-Voice-Assistent [0] |
| 9 | nextcloud/passman [2] | MeadCo/ScriptX.Print.Client [0] | passbolt/passbolt_browser_extension [2] |
| 10 | donutbrowser/donutbrowser [0] | Oefenweb/ansible-mariadb-client [0] | bills-appworks/bsky-sh-cli [0] |

### c07-url-shortener (common)

> a url shortener with click analytics

nDCG@10: Keyword (today) 0.676, Archive only 0.000, Hybrid 0.253
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | 738/awesome-url-shortener [1] | TrueJole/TrueJole.github.io [0] | 738/awesome-url-shortener [1] |
| 2 | urlhum/UrlHum [1] | eyecatchup/MyCountdown-app [0] | TrueJole/TrueJole.github.io [0] |
| 3 | zigotto/googl [0] | alanta/EasyAuthDevProxy [0] | eyecatchup/MyCountdown-app [0] |
| 4 | dogbin/dogbin [1] | naguib101/skyrunner176.github.io [0] | urlhum/UrlHum [1] |
| 5 | Atarity/deploy-your-own-saas [0] | IoannisKtenidis/DataAnalysis-Scripts [0] | zigotto/googl [0] |
| 6 | YOURLS/awesome [1] | qepting91/streamlitransomware [0] | alanta/EasyAuthDevProxy [0] |
| 7 | oxiton-foundation/click-metrics [2] | thomasbeaujean/DoctrineRelationVisualizerBundle [0] | naguib101/skyrunner176.github.io [0] |
| 8 | luadotsh/lua [2] | goloveychuk/yarn-plugin-ignore-deps [0] | dogbin/dogbin [1] |
| 9 | DhananjayThomble/URL-Shortener-App [1] | SphericalKat/eidolon [0] | Atarity/deploy-your-own-saas [0] |
| 10 | public-apis/public-apis [0] | Joohansson/keytools [0] | IoannisKtenidis/DataAnalysis-Scripts [0] |

### c08-recipe (common)

> save recipes and plan weekly meals with a shopping list

nDCG@10: Keyword (today) 0.734, Archive only 0.000, Hybrid 0.360
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | NexaFlowFrance/OpenFamily [1] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |
| 2 | cooklang/cookcli [2] | theabbie/Doodle-Board [0] | NexaFlowFrance/OpenFamily [1] |
| 3 | ivo-toby/mcp-picnic [0] | GalaxiMaster/wordini [0] | theabbie/Doodle-Board [0] |
| 4 | weezerhunter/Supper-Board [1] | AnacondaRecipes/zope.event-feedstock [0] | cooklang/cookcli [2] |
| 5 | matda59/ChoresRewards [0] | php-http/guzzle7-adapter [0] | GalaxiMaster/wordini [0] |
| 6 | olgasafonova/tilbudstrolden-mcp [0] | dcebotarenco/ISDBot [0] | ivo-toby/mcp-picnic [0] |
| 7 | Swiggy/swiggy-mcp-server-manifest [0] | gael-vanderlee/gael-vanderlee.github.io [0] | AnacondaRecipes/zope.event-feedstock [0] |
| 8 | oliexdev/openCook [2] | ondras/wwwsqldesigner [0] | weezerhunter/Supper-Board [1] |
| 9 | NirDiamant/GenAI_Agents [0] | ab-prog1/ab-prog1 [0] | php-http/guzzle7-adapter [0] |
| 10 | jcallaghan/The-Cookbook [1] | Fernando-Sousa-Leal/github-slideshow [0] | matda59/ChoresRewards [0] |

### c09-habit (common)

> habit tracker that shows streaks and reminders

nDCG@10: Keyword (today) 0.850, Archive only 0.000, Hybrid 0.596
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | iSoron/uhabits [2] | qepting91/streamlitransomware [0] | iSoron/uhabits [2] |
| 2 | hesamsheikh/awesome-openclaw-usecases [0] | kawmra/Owl-Timekeeper [0] | qepting91/streamlitransomware [0] |
| 3 | InlitX/streak [2] | gael-vanderlee/gael-vanderlee.github.io [0] | kawmra/Owl-Timekeeper [0] |
| 4 | hemanth/awesome-pwa [0] | sobolevn/wakatime-zsh-plugin [0] | hesamsheikh/awesome-openclaw-usecases [0] |
| 5 | dkhamsing/open-source-ios-apps [0] | Ineichen-Group/NeuroTrialNER [0] | gael-vanderlee/gael-vanderlee.github.io [0] |
| 6 | nikilster/clawflows [0] | milestone-hafnia/trainer-classification [0] | InlitX/streak [2] |
| 7 | Jinjinov/OpenHabitTracker [2] | sarsko/CreuSAT [0] | hemanth/awesome-pwa [0] |
| 8 | 1372Slash/Zenith [0] | theabbie/Doodle-Board [0] | sobolevn/wakatime-zsh-plugin [0] |
| 9 | Lethe044/hermes-life-os [1] | ambarusa/MMM-HomeAssistant [0] | dkhamsing/open-source-ios-apps [0] |
| 10 | jaywcjlove/awesome-mac [0] | eyecatchup/MyCountdown-app [0] | Ineichen-Group/NeuroTrialNER [0] |

### c10-pdf-tools (common)

> merge, split and compress pdf files from the command line

nDCG@10: Keyword (today) 0.846, Archive only 0.000, Hybrid 0.383
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | PDFCraftTool/pdfcraft [1] | richteague/bibchen [0] | richteague/bibchen [0] |
| 2 | Swati4star/Images-to-PDF [0] | naqvis/snappy [0] | PDFCraftTool/pdfcraft [1] |
| 3 | GiovanniPasq/agentic-rag-for-dummies [0] | JRZhang2003/JRZhang2003.github.io [0] | Swati4star/Images-to-PDF [0] |
| 4 | CoderWanFeng/python-office [1] | IoannisKtenidis/DataAnalysis-Scripts [0] | naqvis/snappy [0] |
| 5 | unidoc/unipdf [1] | AAGI-AUS/qcflow-rnaseq [0] | JRZhang2003/JRZhang2003.github.io [0] |
| 6 | alam00000/bentopdf [1] | PackkitLabs/create-packkit-js [0] | GiovanniPasq/agentic-rag-for-dummies [0] |
| 7 | snapotter-hq/SnapOtter [1] | mgb45/MoGapFill [0] | CoderWanFeng/python-office [1] |
| 8 | wasmerio/Python-Scripts [0] | GridGain-Demos/spring-data-training [0] | IoannisKtenidis/DataAnalysis-Scripts [0] |
| 9 | storytold/lightcraft [0] | nvpro-samples/build_all [0] | unidoc/unipdf [1] |
| 10 | Pawandeep-prog/revpdf-release [1] | LuudJacobs/better-bem [0] | AAGI-AUS/qcflow-rnaseq [0] |

### c11-screenshot-ocr (common)

> take a screenshot and extract the text in it with OCR

nDCG@10: Keyword (today) 0.920, Archive only 0.000, Hybrid 0.850
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | ShareX/ShareX [2] | naqvis/snappy [0] | ShareX/ShareX [2] |
| 2 | AzeemIdrisi/PhoneSploit-Pro [0] | contributte/sentry [0] | naqvis/snappy [0] |
| 3 | TheJoeFin/Text-Grab [2] | contributte/bus [0] | contributte/sentry [0] |
| 4 | storytold/pdfcraft [0] | actions-marketplace-validations/boringresearch_find-comments [0] | AzeemIdrisi/PhoneSploit-Pro [0] |
| 5 | ArchiveBox/ArchiveBox [0] | danielhenrymantilla/ext-trait.rs [0] | TheJoeFin/Text-Grab [2] |
| 6 | qxresearch/qxresearch-event-1 [0] | contributte/cache [0] | contributte/bus [0] |
| 7 | j4wg/interview-coder-withoupaywall-opensource [0] | mljar/enrichment [0] | actions-marketplace-validations/boringresearch_find-comments [0] |
| 8 | agent-infra/sandbox [0] | theabbie/Doodle-Board [0] | storytold/pdfcraft [0] |
| 9 | serhii-londar/open-source-mac-os-apps [0] | ab-prog1/ab-prog1 [0] | ArchiveBox/ArchiveBox [0] |
| 10 | h4ckf0r0day/obscura [0] | rust-transit/osm4routing2 [0] | danielhenrymantilla/ext-trait.rs [0] |

### c12-home-dashboard (common)

> a dashboard for my home server showing links to all my self-hosted services

nDCG@10: Keyword (today) 0.450, Archive only 0.000, Hybrid 0.086
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | CapSoftware/Cap [0] | ambarusa/MMM-HomeAssistant [0] | CapSoftware/Cap [0] |
| 2 | ArchiveTeam/grab-site [0] | SamSaffron/blog [0] | ambarusa/MMM-HomeAssistant [0] |
| 3 | frenck/awesome-home-assistant [1] | thomasbeaujean/DoctrineRelationVisualizerBundle [0] | SamSaffron/blog [0] |
| 4 | Moonfin-Client/Plugin [0] | navjeetsingh/gatsby-blog [0] | ArchiveTeam/grab-site [0] |
| 5 | ruvnet/RuView [0] | theabbie/Doodle-Board [0] | thomasbeaujean/DoctrineRelationVisualizerBundle [0] |
| 6 | lissy93/dashy [2] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | frenck/awesome-home-assistant [1] |
| 7 | awesome-jellyfin/awesome-jellyfin [0] | kirtanasingh/AttendanceManagementSystem [0] | navjeetsingh/gatsby-blog [0] |
| 8 | getagentseal/codeburn [0] | IoannisKtenidis/DataAnalysis-Scripts [0] | Moonfin-Client/Plugin [0] |
| 9 | punkpeye/awesome-remote-mcp-servers [0] | ondras/wwwsqldesigner [0] | theabbie/Doodle-Board [0] |
| 10 | mikeroyal/Self-Hosting-Guide [1] | tausani-ah-chong/tausani-portfolio [0] | ruvnet/RuView [0] |

### c13-uptime (common)

> monitor if my websites are up and alert me when they go down

nDCG@10: Keyword (today) 0.661, Archive only 0.000, Hybrid 0.256
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | dgtlmoon/changedetection.io [1] | ambarusa/MMM-HomeAssistant [0] | dgtlmoon/changedetection.io [1] |
| 2 | ripienaar/free-for-dev [0] | eyecatchup/MyCountdown-app [0] | ambarusa/MMM-HomeAssistant [0] |
| 3 | TwiN/gatus [2] | qepting91/streamlitransomware [0] | ripienaar/free-for-dev [0] |
| 4 | nightscout/cgm-remote-monitor [0] | kirtanasingh/AttendanceManagementSystem [0] | eyecatchup/MyCountdown-app [0] |
| 5 | GoogleChrome/lighthouse [0] | kawmra/Owl-Timekeeper [0] | TwiN/gatus [2] |
| 6 | netalertx/NetAlertX [1] | Fernando-Sousa-Leal/github-slideshow [0] | qepting91/streamlitransomware [0] |
| 7 | jivoi/awesome-osint [0] | strolch-li/strolch-wc-ws-observer [0] | nightscout/cgm-remote-monitor [0] |
| 8 | OneUptime/oneuptime [2] | h1w/proxy-pool [0] | kirtanasingh/AttendanceManagementSystem [0] |
| 9 | eidam/cf-workers-status-page [2] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | GoogleChrome/lighthouse [0] |
| 10 | Owloops/updo [2] | gael-vanderlee/gael-vanderlee.github.io [0] | kawmra/Owl-Timekeeper [0] |

### c14-invoice (common)

> create and send invoices for freelance work

nDCG@10: Keyword (today) 0.850, Archive only 0.000, Hybrid 0.731
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | InvoiceShelf/InvoiceShelf [2] | Azure/impact-reporting-samples [0] | InvoiceShelf/InvoiceShelf [2] |
| 2 | cjbarber/ToolsOfTheTrade [0] | gael-vanderlee/gael-vanderlee.github.io [0] | Azure/impact-reporting-samples [0] |
| 3 | Dolibarr/dolibarr [1] | Cyborgscode/Personal-Voice-Assistent [0] | cjbarber/ToolsOfTheTrade [0] |
| 4 | lukasz-madon/awesome-remote-job [0] | beyondcode/helo-laravel [0] | gael-vanderlee/gael-vanderlee.github.io [0] |
| 5 | panshak/accountill [2] | Fernando-Sousa-Leal/github-slideshow [0] | Dolibarr/dolibarr [1] |
| 6 | ashedryden/freelance-contract [0] | facooya/fayos [0] | Cyborgscode/Personal-Voice-Assistent [0] |
| 7 | sam-hosseini/freelancing-in-finland [0] | theabbie/Doodle-Board [0] | lukasz-madon/awesome-remote-job [0] |
| 8 | nabati/freelancing-in-sweden [0] | HjRu94/revello [0] | beyondcode/helo-laravel [0] |
| 9 | ericdodds/the-little-freelancer [0] | lucasdiedrich/node-freeipa [0] | Fernando-Sousa-Leal/github-slideshow [0] |
| 10 | mrzool/invoice-boilerplate [1] | mljar/enrichment [0] | panshak/accountill [2] |

### c15-photo-gallery (common)

> self-hosted photo library with face recognition and albums

nDCG@10: Keyword (today) 0.982, Archive only 0.000, Hybrid 0.781
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | LibrePhotos/librephotos [2] | vaersaagod/focal-point-field [0] | LibrePhotos/librephotos [2] |
| 2 | hooram/ownphotos [2] | Cyborgscode/Personal-Voice-Assistent [0] | vaersaagod/focal-point-field [0] |
| 3 | photoview/photoview [2] | facelessuser/coloraide-extras [0] | hooram/ownphotos [2] |
| 4 | meichthys/foss_photo_libraries [1] | theabbie/Doodle-Board [0] | Cyborgscode/Personal-Voice-Assistent [0] |
| 5 | ncoevoet/facet [2] | HjRu94/revello [0] | photoview/photoview [2] |
| 6 | Haxxnet/Compose-Examples [0] | Joohansson/keytools [0] | facelessuser/coloraide-extras [0] |
| 7 | tlwhittaker/awesome-immich [1] | cwchentw/shlibs [0] | theabbie/Doodle-Board [0] |
| 8 | Dreaming-Codes/immich-cloud-media [0] | danielhenrymantilla/ext-trait.rs [0] | meichthys/foss_photo_libraries [1] |
| 9 | thesnarkitecht/rembrandt [0] | kotanbo/docker-lamp-for-arm [0] | HjRu94/revello [0] |
| 10 | hsa00000/urocissa [1] | thomasbeaujean/DoctrineRelationVisualizerBundle [0] | ncoevoet/facet [2] |

### c16-music-player (common)

> a music player that streams my own mp3 collection

nDCG@10: Keyword (today) 0.662, Archive only 0.000, Hybrid 0.325
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | MoonWalker440/Music-Megathread [0] | Cyborgscode/Personal-Voice-Assistent [0] | Cyborgscode/Personal-Voice-Assistent [0] |
| 2 | awesome-selfhosted/awesome-selfhosted [1] | antonkesy/tap-heading-unity [0] | MoonWalker440/Music-Megathread [0] |
| 3 | rootscripts/riff [0] | ambarusa/MMM-HomeAssistant [0] | awesome-selfhosted/awesome-selfhosted [1] |
| 4 | awesome-jellyfin/awesome-jellyfin [1] | rik-banerjee-git/demo-movie-recom [0] | antonkesy/tap-heading-unity [0] |
| 5 | nodiscc/awesome-linuxaudio [0] | HjRu94/revello [0] | ambarusa/MMM-HomeAssistant [0] |
| 6 | aviaryan/awesome-no-login-web-apps [0] | danielhenrymantilla/ext-trait.rs [0] | rootscripts/riff [0] |
| 7 | Kopuz-org/kopuz [1] | Joohansson/keytools [0] | awesome-jellyfin/awesome-jellyfin [1] |
| 8 | perminder-klair/subwave [0] | trampster/JsonSrcGen [0] | rik-banerjee-git/demo-movie-recom [0] |
| 9 | kushalpandya/Petrichor [1] | qepting91/streamlitransomware [0] | nodiscc/awesome-linuxaudio [0] |
| 10 | BioHapHazard/Freedify [0] | harlow/kinesis-consumer [0] | HjRu94/revello [0] |

### c17-rss (common)

> read rss feeds from news sites in one place

nDCG@10: Keyword (today) 0.987, Archive only 0.000, Hybrid 0.774
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | samuelclay/NewsBlur [2] | futamura/RxPullToRefresh [0] | samuelclay/NewsBlur [2] |
| 2 | FreshRSS/FreshRSS [2] | BookingSync/bookingsync-api [0] | futamura/RxPullToRefresh [0] |
| 3 | RSSNext/Folo [2] | Klajan/DSA-Tools [0] | FreshRSS/FreshRSS [2] |
| 4 | kagisearch/smallweb [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | BookingSync/bookingsync-api [0] |
| 5 | Thysrael/Horizon [1] | LEESANGTAK/takRenamer [0] | Klajan/DSA-Tools [0] |
| 6 | RSS-Bridge/rss-bridge [1] | qepting91/streamlitransomware [0] | RSSNext/Folo [2] |
| 7 | AboutRSS/ALL-about-RSS [1] | JRZhang2003/JRZhang2003.github.io [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |
| 8 | simplifaisoul/osiris [0] | BirjuVachhani/flutter_screwdriver [0] | kagisearch/smallweb [0] |
| 9 | The-Vibe-Company/quivr [0] | andre-campos/andre-campos.github.io [0] | LEESANGTAK/takRenamer [0] |
| 10 | microfeed/microfeed [0] | bills-appworks/bsky-sh-cli [0] | Thysrael/Horizon [1] |

### c18-chatbot-docs (common)

> a chatbot that answers questions about my documents

nDCG@10: Keyword (today) 0.653, Archive only 0.000, Hybrid 0.387
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | amitshekhariitbhu/ai-engineering-interview-questions [0] | Cyborgscode/Personal-Voice-Assistent [0] | Cyborgscode/Personal-Voice-Assistent [0] |
| 2 | ashishpatel26/500-AI-Agents-Projects [0] | GalaxiMaster/wordini [0] | amitshekhariitbhu/ai-engineering-interview-questions [0] |
| 3 | kyrolabs/awesome-langchain [1] | HjRu94/revello [0] | ashishpatel26/500-AI-Agents-Projects [0] |
| 4 | Shubhamsaboo/awesome-llm-apps [1] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | GalaxiMaster/wordini [0] |
| 5 | enescingoz/awesome-n8n-templates [1] | Fernando-Sousa-Leal/github-slideshow [0] | kyrolabs/awesome-langchain [1] |
| 6 | Farzad-R/LLM-Zero-to-Hundred [1] | andre-campos/andre-campos.github.io [0] | HjRu94/revello [0] |
| 7 | Lamatic/AgentKit [0] | eyecatchup/MyCountdown-app [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |
| 8 | OpenMindClub/awesome-chatgpt [0] | sarsko/CreuSAT [0] | Shubhamsaboo/awesome-llm-apps [1] |
| 9 | mlabonne/llm-course [0] | polyvariadic/haskell-challenges [0] | Fernando-Sousa-Leal/github-slideshow [0] |
| 10 | Hannibal046/Awesome-LLM [0] | ab-prog1/ab-prog1 [0] | enescingoz/awesome-n8n-templates [1] |

### r01-beekeeping (rare)

> log hive inspections and honey harvests for beekeeping

nDCG@10: Keyword (today) 0.873, Archive only 0.000, Hybrid 0.294
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | martinhrvn/hive-pal [2] | theabbie/Doodle-Board [0] | theabbie/Doodle-Board [0] |
| 2 | TanushreeN739/Madhu-Marga [1] | HjRu94/revello [0] | martinhrvn/hive-pal [2] |
| 3 | ujwalkumtakar/MadhuMarga [1] | CDEBase/cdm-logger [0] | HjRu94/revello [0] |
| 4 | keerthanahl16/MadhuMarga [1] | Vanilla-IceCream/vite-plugin-fastify [0] | TanushreeN739/Madhu-Marga [1] |
| 5 | sooryakumar9/madhu-marga [1] | BookingSync/bookingsync-api [0] | CDEBase/cdm-logger [0] |
| 6 | jschm42/beeboard2 [2] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | ujwalkumtakar/MadhuMarga [1] |
| 7 | bkfleet1/hive-logistics [2] | AAGI-AUS/qcflow-rnaseq [0] | Vanilla-IceCream/vite-plugin-fastify [0] |
| 8 | Anandkumar-Kambar/Madhu-Marga [2] | raghavthakar/MAPEX [0] | keerthanahl16/MadhuMarga [1] |
| 9 | Chaithanya-12/Madhu-Marga [2] | Fernando-Sousa-Leal/github-slideshow [0] | BookingSync/bookingsync-api [0] |
| 10 | Fahadsheikh5959/Madhu-Marga [2] | Oefenweb/ansible-maven [0] | sooryakumar9/madhu-marga [1] |

### r02-chess-clock (rare)

> a chess clock for over the board games with increment

nDCG@10: Keyword (today) n/a, Archive only n/a, Hybrid n/a
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | peterosterlund2/droidfish [0] | kseo/brainfuck [0] | peterosterlund2/droidfish [0] |
| 2 | michelpereira/awesome-open-source-games [0] | ondras/wwwsqldesigner [0] | kseo/brainfuck [0] |
| 3 | aukspot/dles [0] | ciphergoth/pylambdac [0] | ondras/wwwsqldesigner [0] |
| 4 | shenmareparas/Chess [0] | Ziddykins/Infect [0] | michelpereira/awesome-open-source-games [0] |
| 5 | aviaryan/awesome-no-login-web-apps [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | ciphergoth/pylambdac [0] |
| 6 | amchess/ShashChess [0] | Fernando-Sousa-Leal/github-slideshow [0] | aukspot/dles [0] |
| 7 | vicky002/1000_Projects [0] | tilia/tilia-vobject [0] | Ziddykins/Infect [0] |
| 8 | ornicar/pgn4web [0] | eyecatchup/MyCountdown-app [0] | shenmareparas/Chess [0] |
| 9 | DOBRO/binbo [0] | chordify/redis-schema [0] | aviaryan/awesome-no-login-web-apps [0] |
| 10 | Dash1971/maia-chess-android [0] | mathsgod/markdown-splitter [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |

### r03-midi-sequencer (rare)

> step sequencer that sends MIDI to hardware synths

nDCG@10: Keyword (today) 0.971, Archive only 0.000, Hybrid 0.593
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | isod89/sloop-fm1 [1] | thinger-io/IOTMP-Arduino [0] | thinger-io/IOTMP-Arduino [0] |
| 2 | nodiscc/awesome-linuxaudio [1] | robenkleene/parrot [0] | isod89/sloop-fm1 [1] |
| 3 | webprofusion/OpenAudio [1] | HjRu94/revello [0] | nodiscc/awesome-linuxaudio [1] |
| 4 | joakimeriksson/fm1-emu [0] | theabbie/Doodle-Board [0] | robenkleene/parrot [0] |
| 5 | sudara/awesome-juce [0] | AAGI-AUS/qcflow-rnaseq [0] | webprofusion/OpenAudio [1] |
| 6 | aroum/fm1-custom-fw [1] | mjuenema/python-TSIP [0] | HjRu94/revello [0] |
| 7 | sambanks/octabam [0] | kseo/brainfuck [0] | theabbie/Doodle-Board [0] |
| 8 | Lapin/awesome-music-gear-firmware [0] | curvefi/curve-xdao [0] | joakimeriksson/fm1-emu [0] |
| 9 | n1m21n/Infinite [0] | naqvis/snappy [0] | sudara/awesome-juce [0] |
| 10 | cicloid/awesome-fm-1 [0] | GalaxiMaster/wordini [0] | AAGI-AUS/qcflow-rnaseq [0] |

### r04-ham-radio (rare)

> logbook for amateur ham radio contacts

nDCG@10: Keyword (today) 0.578, Archive only 0.000, Hybrid 0.233
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | DD5HT/awesome-hamradio [1] | theabbie/Doodle-Board [0] | DD5HT/awesome-hamradio [1] |
| 2 | accius/openhamclock [0] | GalaxiMaster/wordini [0] | theabbie/Doodle-Board [0] |
| 3 | kd9taw/Nexus [1] | SamSaffron/blog [0] | GalaxiMaster/wordini [0] |
| 4 | TheMetallists/LoudBang [0] | BookingSync/bookingsync-api [0] | accius/openhamclock [0] |
| 5 | dividebysandwich/sdroxide [0] | conda-forge/yaml-feedstock [0] | SamSaffron/blog [0] |
| 6 | iu8lmc/Decodium-4.0-Core-Shannon [0] | dario-pilori/capacity-functions [0] | kd9taw/Nexus [1] |
| 7 | ftl/hellocontest [2] | HjRu94/revello [0] | BookingSync/bookingsync-api [0] |
| 8 | elisir80/Decodium-4.0-Core-Shannon [0] | ambarusa/MMM-HomeAssistant [0] | TheMetallists/LoudBang [0] |
| 9 | pablots25/ft_ham [0] | CDEBase/cdm-logger [0] | conda-forge/yaml-feedstock [0] |
| 10 | QSOLink/QSOLink [2] | mjuenema/python-TSIP [0] | dividebysandwich/sdroxide [0] |

### r05-knitting (rare)

> design knitting patterns and count rows

nDCG@10: Keyword (today) 0.848, Archive only 0.000, Hybrid 0.398
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | terriko/pyknit [2] | eyecatchup/MyCountdown-app [0] | eyecatchup/MyCountdown-app [0] |
| 2 | mhofmann-Khoury/knit_script [1] | theabbie/Doodle-Board [0] | terriko/pyknit [2] |
| 3 | henmedia/layerling [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | theabbie/Doodle-Board [0] |
| 4 | vinayakkulkarni/nxui [0] | mathsgod/markdown-splitter [0] | mhofmann-Khoury/knit_script [1] |
| 5 | langedoc/stitchmate [1] | ondras/wwwsqldesigner [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |
| 6 | jasonwebb/morphogenesis-resources [0] | harlow/kinesis-consumer [0] | henmedia/layerling [0] |
| 7 | strickvl/knitting-llms [1] | HjRu94/revello [0] | mathsgod/markdown-splitter [0] |
| 8 | emilysaeli/front-end-knitting-patterns [1] | kirtanasingh/AttendanceManagementSystem [0] | vinayakkulkarni/nxui [0] |
| 9 | oampo/yolk [2] | IoannisKtenidis/DataAnalysis-Scripts [0] | ondras/wwwsqldesigner [0] |
| 10 | dectrfov/ICRA2021PaperList [0] | Fernando-Sousa-Leal/github-slideshow [0] | langedoc/stitchmate [1] |

### r06-astronomy (rare)

> plan night sky observations and show which planets are visible tonight

nDCG@10: Keyword (today) 0.457, Archive only 0.000, Hybrid 0.167
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | bilawalsidhu/gods-eye-view [0] | pyspeckit/pyspeckit [0] | pyspeckit/pyspeckit [0] |
| 2 | the-mansi-goel/Ski-dashboard [0] | NOAA-ORR-ERD/lat_lon_parser [0] | bilawalsidhu/gods-eye-view [0] |
| 3 | orbitalindex/awesome-space [1] | GalaxiMaster/wordini [0] | NOAA-ORR-ERD/lat_lon_parser [0] |
| 4 | allisonhorst/stats-illustrations [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | the-mansi-goel/Ski-dashboard [0] |
| 5 | mbiesiad/awesome-astronomy [1] | Fernando-Sousa-Leal/github-slideshow [0] | orbitalindex/awesome-space [1] |
| 6 | uhrichsam4/gods-eye-view [0] | theabbie/Doodle-Board [0] | GalaxiMaster/wordini [0] |
| 7 | elnjensen/Tapir [2] | thomasbeaujean/DoctrineRelationVisualizerBundle [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |
| 8 | UMEP-dev/solweig [0] | raghavthakar/MAPEX [0] | allisonhorst/stats-illustrations [0] |
| 9 | Frank-ZY-Dou/awesome-ai-3d-modeling-robotics [0] | vaersaagod/focal-point-field [0] | mbiesiad/awesome-astronomy [1] |
| 10 | dshanske/simple-location [0] | HjRu94/revello [0] | Fernando-Sousa-Leal/github-slideshow [0] |

### r07-plant-watering (rare)

> soil moisture sensor that waters plants automatically with an arduino

nDCG@10: Keyword (today) 0.973, Archive only 0.000, Hybrid 0.783
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | jonathanrjpereira/Automatic-Plant-Watering-System [2] | thinger-io/IOTMP-Arduino [0] | jonathanrjpereira/Automatic-Plant-Watering-System [2] |
| 2 | SmartThingsDIY/arduino-uno-aws-irrigation-system [2] | ambarusa/MMM-HomeAssistant [0] | thinger-io/IOTMP-Arduino [0] |
| 3 | chowzzzz/smartgarden [1] | yasaisen/hardPrompt2softPrompt [0] | SmartThingsDIY/arduino-uno-aws-irrigation-system [2] |
| 4 | Shishir3D/PlantMonitoringSystem [2] | HjRu94/revello [0] | ambarusa/MMM-HomeAssistant [0] |
| 5 | AkashKobal/solar-based-remote-control-smart-garden [1] | GalaxiMaster/wordini [0] | chowzzzz/smartgarden [1] |
| 6 | protontypes/open-sustainable-technology [0] | Fernando-Sousa-Leal/github-slideshow [0] | yasaisen/hardPrompt2softPrompt [0] |
| 7 | JamesMcCarthy79/Home-Assistant-Config [0] | conda-forge/orthority-feedstock [0] | Shishir3D/PlantMonitoringSystem [2] |
| 8 | wenzaca/SmartGarden [1] | Cyborgscode/Personal-Voice-Assistent [0] | HjRu94/revello [0] |
| 9 | Vaishnavi-Pothugunta/Automatic-Watering-System [1] | pyspeckit/pyspeckit [0] | AkashKobal/solar-based-remote-control-smart-garden [1] |
| 10 | satellite-image-deep-learning/techniques [0] | IoannisKtenidis/DataAnalysis-Scripts [0] | GalaxiMaster/wordini [0] |

### r08-bird-sound (rare)

> identify birds from a recording of their song

nDCG@10: Keyword (today) 0.551, Archive only 0.000, Hybrid 0.174
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | AgaMiko/bird-recognition-review [1] | robenkleene/parrot [0] | robenkleene/parrot [0] |
| 2 | jim-schwoebel/voice_datasets [0] | kawmra/Owl-Timekeeper [0] | AgaMiko/bird-recognition-review [1] |
| 3 | MoonWalker440/Music-Megathread [0] | theabbie/Doodle-Board [0] | kawmra/Owl-Timekeeper [0] |
| 4 | Yuan-ManX/ai-audio-datasets [0] | cwchentw/shlibs [0] | jim-schwoebel/voice_datasets [0] |
| 5 | ghimiresunil/Top-AI-Tools [0] | Cyborgscode/Personal-Voice-Assistent [0] | theabbie/Doodle-Board [0] |
| 6 | VoltAgent/awesome-openclaw-skills [0] | HjRu94/revello [0] | MoonWalker440/Music-Megathread [0] |
| 7 | josafatburmeister/BirdSongIdentification [2] | vaersaagod/focal-point-field [0] | cwchentw/shlibs [0] |
| 8 | adamoberley/HABirdDashboard [0] | Fernando-Sousa-Leal/github-slideshow [0] | Yuan-ManX/ai-audio-datasets [0] |
| 9 | eselkin/awesome-computational-neuroscience [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | Cyborgscode/Personal-Voice-Assistent [0] |
| 10 | public-apis/public-apis [0] | Joohansson/keytools [0] | ghimiresunil/Top-AI-Tools [0] |

### r09-genealogy (rare)

> build a family tree and import GEDCOM files

nDCG@10: Keyword (today) 0.946, Archive only 0.000, Hybrid 0.570
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | fisharebest/webtrees [2] | facooya/fayos [0] | fisharebest/webtrees [2] |
| 2 | michelesalvador/FamilyGem [2] | JRZhang2003/JRZhang2003.github.io [0] | facooya/fayos [0] |
| 3 | FamilySearch/gedcom5-java [1] | LuudJacobs/better-bem [0] | michelesalvador/FamilyGem [2] |
| 4 | todrobbins/awesome-gedcom [1] | theabbie/Doodle-Board [0] | JRZhang2003/JRZhang2003.github.io [0] |
| 5 | oh-kay-blanket/family-plot [1] | mjuenema/python-TSIP [0] | FamilySearch/gedcom5-java [1] |
| 6 | MGeurts/genealogy [2] | gechr/yamlfmt [0] | LuudJacobs/better-bem [0] |
| 7 | Minh-Tam-Solution/AncestorTree [1] | AAGI-AUS/qcflow-rnaseq [0] | todrobbins/awesome-gedcom [1] |
| 8 | liberusoftware/project-genealogy-laravel-filament [2] | rust-transit/osm4routing2 [0] | theabbie/Doodle-Board [0] |
| 9 | Jisco/VisualFamilyTree [1] | Cyborgscode/Personal-Voice-Assistent [0] | mjuenema/python-TSIP [0] |
| 10 | nigelhorne/gedcom [1] | gugod/sitebrew [0] | oh-kay-blanket/family-plot [1] |

### r10-sheet-music (rare)

> turn a photo of sheet music into a playable midi file

nDCG@10: Keyword (today) n/a, Archive only n/a, Hybrid n/a
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | ellisonleao/magictools [0] | facooya/fayos [0] | ellisonleao/magictools [0] |
| 2 | scenario-labs/skills [0] | cwchentw/shlibs [0] | facooya/fayos [0] |
| 3 | ghimiresunil/Top-AI-Tools [0] | theabbie/Doodle-Board [0] | cwchentw/shlibs [0] |
| 4 | img2threejs/img2threejs [0] | antonkesy/tap-heading-unity [0] | scenario-labs/skills [0] |
| 5 | goabstract/Awesome-Design-Tools [0] | HjRu94/revello [0] | theabbie/Doodle-Board [0] |
| 6 | Axorax/awesome-free-apps [0] | MeadCo/ScriptX.Print.Client [0] | ghimiresunil/Top-AI-Tools [0] |
| 7 | vsouza/awesome-ios [0] | Oefenweb/ansible-mariadb-client [0] | antonkesy/tap-heading-unity [0] |
| 8 | ai-boost/awesome-image-video-prompts [0] | mjuenema/python-TSIP [0] | img2threejs/img2threejs [0] |
| 9 | codepawl/creator-generalist [0] | SphericalKat/eidolon [0] | goabstract/Awesome-Design-Tools [0] |
| 10 | public-apis/public-apis [0] | happytianhao/TOP [0] | HjRu94/revello [0] |

### r11-tide (rare)

> tide times and predictions for a fishing trip

nDCG@10: Keyword (today) 0.650, Archive only 0.000, Hybrid 0.195
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | protontypes/open-sustainable-technology [0] | NOAA-ORR-ERD/lat_lon_parser [0] | NOAA-ORR-ERD/lat_lon_parser [0] |
| 2 | mkearney/shinyapps_links [0] | theabbie/Doodle-Board [0] | protontypes/open-sustainable-technology [0] |
| 3 | lukastr96/tas-fishing-assistant [1] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | mkearney/shinyapps_links [0] |
| 4 | dnyandipbhalerao336-cloud/ReelForge-MoggyDay-TrainerHub [0] | Fernando-Sousa-Leal/github-slideshow [0] | theabbie/Doodle-Board [0] |
| 5 | csgo-adc/fishing-nz [1] | mjuenema/python-TSIP [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |
| 6 | ainastrahnet/Ice-Fishing-Tide [1] | gael-vanderlee/gael-vanderlee.github.io [0] | lukastr96/tas-fishing-assistant [1] |
| 7 | SNXFFBXXTS/essexfishing [0] | pyspeckit/pyspeckit [0] | Fernando-Sousa-Leal/github-slideshow [0] |
| 8 | marcusaug123/fishing-weather-app [1] | AnacondaRecipes/zope.event-feedstock [0] | dnyandipbhalerao336-cloud/ReelForge-MoggyDay-TrainerHub [0] |
| 9 | vinnimous/TideRunner [1] | raghavthakar/MAPEX [0] | mjuenema/python-TSIP [0] |
| 10 | YutengMei/Fish-Web [1] | tilia/tilia-event [0] | csgo-adc/fishing-nz [1] |

### r12-board-game-ai (rare)

> an engine that plays the board game go against me

nDCG@10: Keyword (today) 1.000, Archive only 0.000, Hybrid 0.920
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | lightvector/KataGo [2] | HjRu94/revello [0] | lightvector/KataGo [2] |
| 2 | sanderland/katrain [2] | Lukaria/Unity_Game [0] | HjRu94/revello [0] |
| 3 | michelpereira/awesome-open-source-games [0] | antonkesy/tap-heading-unity [0] | sanderland/katrain [2] |
| 4 | thomasahle/sunfish [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | Lukaria/Unity_Game [0] |
| 5 | NeymarL/ChineseChess-AlphaZero [0] | Ziddykins/Infect [0] | antonkesy/tap-heading-unity [0] |
| 6 | flame-engine/awesome-flame [0] | theabbie/Doodle-Board [0] | michelpereira/awesome-open-source-games [0] |
| 7 | peterosterlund2/droidfish [0] | qepting91/streamlitransomware [0] | thomasahle/sunfish [0] |
| 8 | WhiteTowerAI/ohmygame [0] | gdquest-demos/godot-2d-builder [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |
| 9 | learn-co-students/ttt-with-ai-project-v-000 [0] | mjuenema/python-TSIP [0] | Ziddykins/Infect [0] |
| 10 | fsmosca/Python-Easy-Chess-GUI [0] | raghavthakar/MAPEX [0] | NeymarL/ChineseChess-AlphaZero [0] |

### l01-rust-cli-http (language)

> a command line http client written in rust

nDCG@10: Keyword (today) 0.338, Archive only 0.296, Hybrid 0.338
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | yt-dlp/yt-dlp [0] | HjRu94/revello [0] | yt-dlp/yt-dlp [0] |
| 2 | tldr-pages/tldr [0] | poohlaha/rust-tools [1] | HjRu94/revello [0] |
| 3 | linera-io/linera-protocol [0] | h1w/proxy-pool [0] | tldr-pages/tldr [0] |
| 4 | joeferner/redis-commander [0] | Joohansson/keytools [0] | poohlaha/rust-tools [1] |
| 5 | ogham/dog [1] | rust-transit/osm4routing2 [0] | h1w/proxy-pool [0] |
| 6 | safe6Sec/command [0] | danielhenrymantilla/ext-trait.rs [0] | linera-io/linera-protocol [0] |
| 7 | denji/awesome-http-benchmark [1] | salrashid123/golang-jwt-pqc [0] | joeferner/redis-commander [0] |
| 8 | ffuf/ffuf [0] | sarsko/CreuSAT [0] | Joohansson/keytools [0] |
| 9 | mr-karan/doggo [0] | ondras/wwwsqldesigner [0] | rust-transit/osm4routing2 [0] |
| 10 | alebcay/awesome-shell [0] | Klajan/DSA-Tools [0] | ogham/dog [1] |

### l02-go-reverse-proxy (language)

> reverse proxy with automatic https in go

nDCG@10: Keyword (today) 0.622, Archive only 0.000, Hybrid 0.290
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | quic-go/quic-go [0] | alanta/EasyAuthDevProxy [0] | quic-go/quic-go [0] |
| 2 | drk1wi/Modlishka [1] | h1w/proxy-pool [0] | alanta/EasyAuthDevProxy [0] |
| 3 | traefik/traefik [2] | oinume/algo [0] | drk1wi/Modlishka [1] |
| 4 | linuxserver/reverse-proxy-confs [1] | vulkoingim/zrok-operator [0] | h1w/proxy-pool [0] |
| 5 | grpc-ecosystem/grpc-gateway [0] | BitcoinSchema/go-bob [0] | oinume/algo [0] |
| 6 | jpillora/chisel [0] | cohesivestack/valgo [0] | traefik/traefik [2] |
| 7 | fatedier/frp [1] | gechr/yamlfmt [0] | linuxserver/reverse-proxy-confs [1] |
| 8 | miekg/dns [0] | curvefi/curve-xdao [0] | vulkoingim/zrok-operator [0] |
| 9 | tobychui/zoraxy [2] | TridotsTech/go1_meet [0] | grpc-ecosystem/grpc-gateway [0] |
| 10 | snail007/goproxy [1] | HjRu94/revello [0] | BitcoinSchema/go-bob [0] |

### l03-flutter-expense (language)

> flutter mobile app for splitting expenses with friends

nDCG@10: Keyword (today) 0.865, Archive only 0.000, Hybrid 0.399
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | keyur-369/split_expenses [2] | GalaxiMaster/wordini [0] | GalaxiMaster/wordini [0] |
| 2 | GDG-IGDTUW/Mobile-Dev [0] | Fernando-Sousa-Leal/github-slideshow [0] | keyur-369/split_expenses [2] |
| 3 | vijay-kesanakurthi/swap-pay [2] | BirjuVachhani/flutter_screwdriver [0] | Fernando-Sousa-Leal/github-slideshow [0] |
| 4 | dinilH/Tally [1] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | GDG-IGDTUW/Mobile-Dev [0] |
| 5 | SarbajitPbappy/MAD-Final [0] | SoFluffyOS/gms_check [0] | BirjuVachhani/flutter_screwdriver [0] |
| 6 | DFY-NCSU/CoinCanvas [1] | HjRu94/revello [0] | vijay-kesanakurthi/swap-pay [2] |
| 7 | T-E-E-N-A/team-07-Travel-Planner-with-Itinerary-Expense-Splitter- [1] | mjuenema/python-TSIP [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |
| 8 | Jetti-Ganesh/SmartSplit [1] | mathsgod/markdown-splitter [0] | dinilH/Tally [1] |
| 9 | Vidushi-Infotech/kharchasplit_revamp [1] | futamura/RxPullToRefresh [0] | SoFluffyOS/gms_check [0] |
| 10 | riyajain137/SplitSmart [2] | DFE-Digital/support-for-social-workers [0] | SarbajitPbappy/MAD-Final [0] |

### l04-react-kanban (language)

> kanban board built with react and drag and drop

nDCG@10: Keyword (today) 0.525, Archive only 0.000, Hybrid 0.252
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | ColorlibHQ/gentelella [0] | Fernando-Sousa-Leal/github-slideshow [0] | ColorlibHQ/gentelella [0] |
| 2 | Kiranism/next-shadcn-dashboard-starter [0] | arif-js/datalogz-custom-tree-select [0] | Fernando-Sousa-Leal/github-slideshow [0] |
| 3 | anoopcodehack/DevBoard [2] | theabbie/Doodle-Board [0] | arif-js/datalogz-custom-tree-select [0] |
| 4 | JohnRiceML/clawport-ui [0] | LEESANGTAK/takRenamer [0] | Kiranism/next-shadcn-dashboard-starter [0] |
| 5 | trungvose/jira-clone-angular [1] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | theabbie/Doodle-Board [0] |
| 6 | Kiranism/tanstack-start-dashboard [0] | ab-prog1/ab-prog1 [0] | anoopcodehack/DevBoard [2] |
| 7 | birobirobiro/awesome-shadcn-ui [0] | BitcoinSchema/go-bob [0] | LEESANGTAK/takRenamer [0] |
| 8 | Hesam-Dearboy/kanban-task-management-react-tailwind [2] | kseo/brainfuck [0] | JohnRiceML/clawport-ui [0] |
| 9 | keenthemes/reui [0] | matisku/tig-stack [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |
| 10 | eneskirca/nodeterm [0] | gefercan2/reactJS_exercises [0] | trungvose/jira-clone-angular [1] |

### l05-python-scraper (language)

> python library to scrape websites that use javascript

nDCG@10: Keyword (today) 0.694, Archive only 0.000, Hybrid 0.321
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | vinta/awesome-python [0] | IoannisKtenidis/DataAnalysis-Scripts [0] | vinta/awesome-python [0] |
| 2 | D4Vinci/Scrapling [2] | andre-campos/andre-campos.github.io [0] | IoannisKtenidis/DataAnalysis-Scripts [0] |
| 3 | practical-tutorials/project-based-learning [0] | navjeetsingh/gatsby-blog [0] | andre-campos/andre-campos.github.io [0] |
| 4 | apify/crawlee-python [2] | ab-prog1/ab-prog1 [0] | D4Vinci/Scrapling [2] |
| 5 | BruceDone/awesome-crawler [1] | Fernando-Sousa-Leal/github-slideshow [0] | practical-tutorials/project-based-learning [0] |
| 6 | apify/crawlee [1] | naguib101/skyrunner176.github.io [0] | navjeetsingh/gatsby-blog [0] |
| 7 | Anorov/cloudflare-scrape [1] | MeadCo/ScriptX.Print.Client [0] | ab-prog1/ab-prog1 [0] |
| 8 | dhamaniasad/HeadlessBrowsers [1] | Joohansson/keytools [0] | apify/crawlee-python [2] |
| 9 | unclecode/crawl4ai [2] | Cyborgscode/Personal-Voice-Assistent [0] | BruceDone/awesome-crawler [1] |
| 10 | MunGell/awesome-for-beginners [0] | milestone-hafnia/trainer-classification [0] | Fernando-Sousa-Leal/github-slideshow [0] |

### l06-swift-weather (language)

> weather app for iphone in swiftui

nDCG@10: Keyword (today) 1.000, Archive only 0.000, Hybrid 1.000
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | dkhamsing/open-source-ios-apps [1] | kawmra/Owl-Timekeeper [0] | dkhamsing/open-source-ios-apps [1] |
| 2 | apple/sample-food-truck [0] | SoFluffyOS/gms_check [0] | kawmra/Owl-Timekeeper [0] |
| 3 | zzanehip/The-OldOS-Project [0] | futamura/RxPullToRefresh [0] | SoFluffyOS/gms_check [0] |
| 4 | Juanpe/About-SwiftUI [0] | thinger-io/IOTMP-Arduino [0] | apple/sample-food-truck [0] |
| 5 | onmyway133/awesome-swiftui [0] | BirjuVachhani/flutter_screwdriver [0] | futamura/RxPullToRefresh [0] |
| 6 | skiptools/skip [0] | HjRu94/revello [0] | zzanehip/The-OldOS-Project [0] |
| 7 | matteocrippa/awesome-swift [0] | IoannisKtenidis/DataAnalysis-Scripts [0] | Juanpe/About-SwiftUI [0] |
| 8 | everettjf/scriptwidget [0] | eyecatchup/MyCountdown-app [0] | thinger-io/IOTMP-Arduino [0] |
| 9 | uhub/awesome-swift [0] | XiaWei-NEU/XiaWei-NEU.github.io [0] | BirjuVachhani/flutter_screwdriver [0] |
| 10 | VoltAgent/awesome-openclaw-skills [0] | pyspeckit/pyspeckit [0] | onmyway133/awesome-swiftui [0] |

### l07-kotlin-reader (language)

> android ebook reader written in kotlin

nDCG@10: Keyword (today) 0.971, Archive only 0.000, Hybrid 0.592
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | Pool-Of-Tears/Myne [2] | SoFluffyOS/gms_check [0] | SoFluffyOS/gms_check [0] |
| 2 | binaryshrey/Awesome-Android-Open-Source-Projects [1] | naqvis/snappy [0] | Pool-Of-Tears/Myne [2] |
| 3 | MunGell/awesome-for-beginners [0] | larmic/spring-boot-demos [0] | naqvis/snappy [0] |
| 4 | opds-community/awesome-opds [1] | Oefenweb/ansible-maven [0] | binaryshrey/Awesome-Android-Open-Source-Projects [1] |
| 5 | trypsynth/paperback [1] | HjRu94/revello [0] | MunGell/awesome-for-beginners [0] |
| 6 | readium/awesome-readium [1] | GalaxiMaster/wordini [0] | larmic/spring-boot-demos [0] |
| 7 | EvanLi/Github-Ranking [0] | ab-prog1/ab-prog1 [0] | Oefenweb/ansible-maven [0] |
| 8 | auctors/free-lunch [0] | anhoder/anhoder [0] | opds-community/awesome-opds [1] |
| 9 | aljazceru/awesome-nostr [0] | salrashid123/golang-jwt-pqc [0] | HjRu94/revello [0] |
| 10 | Silo-Server/silo-android [0] | chordify/redis-schema [0] | trypsynth/paperback [1] |

### l08-typescript-orm (language)

> type safe database orm for typescript

nDCG@10: Keyword (today) 0.573, Archive only 0.000, Hybrid 0.417
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | ljlm0402/typescript-express-starter [0] | matisku/tig-stack [0] | matisku/tig-stack [0] |
| 2 | kriasoft/react-starter-kit [0] | 54145a/54145a.github.io [0] | ljlm0402/typescript-express-starter [0] |
| 3 | mikro-orm/mikro-orm [2] | ondras/wwwsqldesigner [0] | kriasoft/react-starter-kit [0] |
| 4 | marcj/deepkit [1] | CDEBase/cdm-logger [0] | 54145a/54145a.github.io [0] |
| 5 | zenstackhq/zenstack [2] | kawmra/Owl-Timekeeper [0] | ondras/wwwsqldesigner [0] |
| 6 | ixartz/Next-js-Boilerplate [0] | criipto/node-cache [0] | mikro-orm/mikro-orm [2] |
| 7 | sindresorhus/awesome-nodejs [0] | PackkitLabs/create-packkit-js [0] | CDEBase/cdm-logger [0] |
| 8 | AmanVarshney01/create-better-t-stack [0] | u17g/u17g.com [0] | marcj/deepkit [1] |
| 9 | ixartz/SaaS-Boilerplate [0] | lucasdiedrich/node-freeipa [0] | kawmra/Owl-Timekeeper [0] |
| 10 | chentsulin/awesome-graphql [0] | IoannisKtenidis/DataAnalysis-Scripts [0] | zenstackhq/zenstack [2] |

### l09-cpp-game-engine (language)

> small 2d game engine in c++

nDCG@10: Keyword (today) 0.629, Archive only 0.000, Hybrid 0.440
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | codecrafters-io/build-your-own-x [0] | ChivenZhang/OpenUI [0] | codecrafters-io/build-your-own-x [0] |
| 2 | ellisonleao/magictools [1] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | ChivenZhang/OpenUI [0] |
| 3 | fffaraz/awesome-cpp [1] | gdquest-demos/godot-2d-builder [0] | ellisonleao/magictools [1] |
| 4 | cocos2d/cocos2d-x [2] | HjRu94/revello [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |
| 5 | Kavex/GameDev-Resources [1] | Ziddykins/Infect [0] | fffaraz/awesome-cpp [1] |
| 6 | r-lyeh/single_file_libs [0] | Lukaria/Unity_Game [0] | gdquest-demos/godot-2d-builder [0] |
| 7 | htdt/godogen [0] | antonkesy/tap-heading-unity [0] | cocos2d/cocos2d-x [2] |
| 8 | Calinou/awesome-godot [0] | mjuenema/python-TSIP [0] | HjRu94/revello [0] |
| 9 | cocos2d/cocos2d-html5 [1] | yasaisen/hardPrompt2softPrompt [0] | Ziddykins/Infect [0] |
| 10 | gamedev-skills/awesome-gamedev-agent-skills [0] | cpp-prism/prism_all [0] | Kavex/GameDev-Resources [1] |

### l10-elixir-realtime (language)

> realtime multiplayer backend using elixir and phoenix

nDCG@10: Keyword (today) 0.746, Archive only 0.000, Hybrid 0.296
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | h4cc/awesome-elixir [1] | ondras/wwwsqldesigner [0] | ondras/wwwsqldesigner [0] |
| 2 | practical-tutorials/project-based-learning [0] | ab-prog1/ab-prog1 [0] | h4cc/awesome-elixir [1] |
| 3 | facundofarias/awesome-websockets [0] | alanta/EasyAuthDevProxy [0] | practical-tutorials/project-based-learning [0] |
| 4 | mikehostetler/awesome-selfhosted-elixir [0] | Exupery/pvpleaderboardupdater [0] | ab-prog1/ab-prog1 [0] |
| 5 | greyhwndz/awesome-elixir-posts [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | facundofarias/awesome-websockets [0] |
| 6 | insthync/awesome-unity3d [0] | Vanilla-IceCream/vite-plugin-fastify [0] | alanta/EasyAuthDevProxy [0] |
| 7 | cristobalcl/awesome-startup-stack [0] | klsecservices/MDR-integrations [0] | Exupery/pvpleaderboardupdater [0] |
| 8 | connect2cpraveena/my_tech_resources [0] | danini-the-panini/findyml [0] | mikehostetler/awesome-selfhosted-elixir [0] |
| 9 | Correia-jpv/fucking-awesome-elixir [1] | Cyborgscode/Personal-Voice-Assistent [0] | greyhwndz/awesome-elixir-posts [0] |
| 10 | happycodrz/phoenix-apps [1] | Fernando-Sousa-Leal/github-slideshow [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |

### l11-bash-dotfiles (language)

> shell scripts to manage my dotfiles across machines

nDCG@10: Keyword (today) 0.634, Archive only 0.192, Hybrid 0.447
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | webpro/awesome-dotfiles [1] | nycynik/dotFiles [1] | webpro/awesome-dotfiles [1] |
| 2 | jdx/mise [0] | needcaffeine/dotfiles [1] | nycynik/dotFiles [1] |
| 3 | daviwil/dotfiles [1] | GridGain-Demos/spring-data-training [0] | needcaffeine/dotfiles [1] |
| 4 | anishathalye/dotbot [2] | scampersand/envbash-python [0] | jdx/mise [0] |
| 5 | hendrikmi/dotfiles [1] | cwchentw/shlibs [0] | daviwil/dotfiles [1] |
| 6 | sindresorhus/awesome [0] | bills-appworks/bsky-sh-cli [0] | GridGain-Demos/spring-data-training [0] |
| 7 | natelandau/dotfiles [2] | IoannisKtenidis/DataAnalysis-Scripts [0] | anishathalye/dotbot [2] |
| 8 | freekmurze/dotfiles [1] | matisku/tig-stack [0] | scampersand/envbash-python [0] |
| 9 | haacked/dotfiles [2] | Cyborgscode/Personal-Voice-Assistent [0] | cwchentw/shlibs [0] |
| 10 | moul/awesome-ssh [0] | projectsyn/lieutenant-operator [0] | hendrikmi/dotfiles [1] |

### l12-wasm-image (language)

> resize and edit images in the browser with webassembly

nDCG@10: Keyword (today) 0.504, Archive only 0.000, Hybrid 0.328
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | DustinBrett/daedalOS [0] | ondras/wwwsqldesigner [0] | ondras/wwwsqldesigner [0] |
| 2 | PDFCraftTool/pdfcraft [0] | CaselIT/hash-set-map [0] | DustinBrett/daedalOS [0] |
| 3 | CH563/shot-easy-website [1] | Fernando-Sousa-Leal/github-slideshow [0] | CaselIT/hash-set-map [0] |
| 4 | silvia-odwyer/photon [2] | Klajan/DSA-Tools [0] | PDFCraftTool/pdfcraft [0] |
| 5 | storytold/pdfcraft [0] | thomasbeaujean/DoctrineRelationVisualizerBundle [0] | Fernando-Sousa-Leal/github-slideshow [0] |
| 6 | bradtraversy/design-resources-for-developers [0] | LuudJacobs/better-bem [0] | CH563/shot-easy-website [1] |
| 7 | AdrienTorris/awesome-blazor [0] | JRZhang2003/JRZhang2003.github.io [0] | silvia-odwyer/photon [2] |
| 8 | Volcomix/virtual-background [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | Klajan/DSA-Tools [0] |
| 9 | storytold/effectcraft [0] | MeadCo/ScriptX.Print.Client [0] | thomasbeaujean/DoctrineRelationVisualizerBundle [0] |
| 10 | imagescript/ImageScript [1] | CaselIT/json-set-map [0] | storytold/pdfcraft [0] |

### n01-de-haushaltsbuch (non_english)

> Haushaltsbuch App um meine Ausgaben zu verfolgen

nDCG@10: Keyword (today) n/a, Archive only n/a, Hybrid n/a
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | semihkilla/CodeKlar [0] | eyecatchup/MyCountdown-app [0] | eyecatchup/MyCountdown-app [0] |
| 2 |  | HjRu94/revello [0] | semihkilla/CodeKlar [0] |
| 3 |  | theabbie/Doodle-Board [0] | HjRu94/revello [0] |
| 4 |  | tilia/tilia-xml [0] | theabbie/Doodle-Board [0] |
| 5 |  | tilia/tilia-http [0] | tilia/tilia-xml [0] |
| 6 |  | eska-muc/dbvisualizer [0] | tilia/tilia-http [0] |
| 7 |  | Oefenweb/ansible-maven [0] | eska-muc/dbvisualizer [0] |
| 8 |  | anhoder/anhoder [0] | Oefenweb/ansible-maven [0] |
| 9 |  | rik-banerjee-git/demo-movie-recom [0] | anhoder/anhoder [0] |
| 10 |  | tausani-ah-chong/tausani-portfolio [0] | rik-banerjee-git/demo-movie-recom [0] |

### n02-es-recetas (non_english)

> aplicación para guardar recetas de cocina

nDCG@10: Keyword (today) 0.561, Archive only 0.000, Hybrid 0.108
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | GxJohan/recetas-estudiantes [1] | Wendel-de-Andrade/DriveSlide [0] | Wendel-de-Andrade/DriveSlide [0] |
| 2 | khriztianmoreno/apollo-client-workshop-react [0] | kawmra/Owl-Timekeeper [0] | GxJohan/recetas-estudiantes [1] |
| 3 | facundouferer/CursoDeJava [0] | HjRu94/revello [0] | kawmra/Owl-Timekeeper [0] |
| 4 | FernandoCalmet/design-patterns [0] | cykret99/GanttChart [0] | khriztianmoreno/apollo-client-workshop-react [0] |
| 5 | jhoacar-utn/course-node-6822-03-2022 [0] | anhoder/anhoder [0] | facundouferer/CursoDeJava [0] |
| 6 | FernandoHuilca/web-recetario [2] | eyecatchup/MyCountdown-app [0] | HjRu94/revello [0] |
| 7 | mmaria145/appcook [1] | harlow/kinesis-consumer [0] | FernandoCalmet/design-patterns [0] |
| 8 | AW-SocialTechOrg/cookguide_report_os [0] | oranfry/jars-refreshd [0] | cykret99/GanttChart [0] |
| 9 | acmazoh/Gestion_pedidos_inventario [0] | XiaWei-NEU/XiaWei-NEU.github.io [0] | anhoder/anhoder [0] |
| 10 | iC0d1g0/AcomerYa [2] | enbrea/enbrea.konsoli [0] | jhoacar-utn/course-node-6822-03-2022 [0] |

### n03-fr-gestion-taches (non_english)

> application de gestion de tâches pour une petite équipe

nDCG@10: Keyword (today) 0.653, Archive only 0.390, Hybrid 0.637
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | liorchamla/amu-tp-vanilla-todo [1] | cykret99/GanttChart [1] | liorchamla/amu-tp-vanilla-todo [1] |
| 2 | Aif4thah/Dojo-101 [0] | kawmra/Owl-Timekeeper [0] | cykret99/GanttChart [1] |
| 3 | rarianaAina/mes-outils [0] | PackkitLabs/create-packkit-js [0] | kawmra/Owl-Timekeeper [0] |
| 4 | profcfuhrmanets/log210-enonce-lab1 [0] | Wendel-de-Andrade/DriveSlide [0] | Aif4thah/Dojo-101 [0] |
| 5 | romquenin/home-assistant-config-fr [0] | IoannisKtenidis/Task-Automation-Tool [0] | PackkitLabs/create-packkit-js [0] |
| 6 | liorchamla/amu-tp-react-todo [1] | matisku/tig-stack [0] | rarianaAina/mes-outils [0] |
| 7 | Emsi-students-2023/python-exercises [0] | ondras/wwwsqldesigner [0] | profcfuhrmanets/log210-enonce-lab1 [0] |
| 8 | HUB-HUmanBeing/SystemD [1] | sobolevn/wakatime-zsh-plugin [0] | Wendel-de-Andrade/DriveSlide [0] |
| 9 | moovai/technical-test-data-engineer [0] | contributte/api-docu [0] | romquenin/home-assistant-config-fr [0] |
| 10 | priximmo/sommaire-xavki-devops-fr [0] | IoannisKtenidis/DataAnalysis-Scripts [0] | IoannisKtenidis/Task-Automation-Tool [0] |

### n04-pt-financas (non_english)

> controle de finanças pessoais com gráficos

nDCG@10: Keyword (today) 0.511, Archive only 0.000, Hybrid 0.098
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | DelphiCreative/Projetos [0] | juaoantonio/clone-tabnews [0] | DelphiCreative/Projetos [0] |
| 2 | estevanmaito/apenas-crie-websites [0] | Wendel-de-Andrade/DriveSlide [0] | juaoantonio/clone-tabnews [0] |
| 3 | CFBruna/smart-expense-analyzer [1] | vaersaagod/focal-point-field [0] | estevanmaito/apenas-crie-websites [0] |
| 4 | arthurspk/guiadevbrasil [0] | HjRu94/revello [0] | Wendel-de-Andrade/DriveSlide [0] |
| 5 | ES-Project-2024-2/Gestao-de-gastos-pessoais [1] | dcebotarenco/ISDBot [0] | vaersaagod/focal-point-field [0] |
| 6 | NeiltonSeguins/4461-react-context-api [0] | beyondcode/helo-laravel [0] | CFBruna/smart-expense-analyzer [1] |
| 7 | 07Dalmaso/GestaoPessoal [1] | mathsgod/markdown-splitter [0] | arthurspk/guiadevbrasil [0] |
| 8 | Raullize/conta-comigo [2] | gefercan2/reactJS_exercises [0] | HjRu94/revello [0] |
| 9 | LucasArend/Orion-gestor-de-financas [2] | duereg/no-cliches [0] | dcebotarenco/ISDBot [0] |
| 10 | pycodebr/finanpy_v2 [1] | cykret99/GanttChart [0] | ES-Project-2024-2/Gestao-de-gastos-pessoais [1] |

### n05-ja-kakeibo (non_english)

> 家計簿アプリ

nDCG@10: Keyword (today) 0.613, Archive only 0.000, Hybrid 0.264
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | gohandson/accountbook-ja [1] | cykret99/GanttChart [0] | gohandson/accountbook-ja [1] |
| 2 | ochyai/open-japan-politech-platform [0] | yelog/layui-soul-table [0] | cykret99/GanttChart [0] |
| 3 | tomosuke-chiba/kou-ai-training-sandbox [0] | IoannisKtenidis/DataAnalysis-Scripts [0] | yelog/layui-soul-table [0] |
| 4 | S-H-GAMELINKS/MyFirstRails [0] | tetezi/workspaceAdmin [0] | ochyai/open-japan-politech-platform [0] |
| 5 | qlitre/django-mdb-kakeibo [2] | facooya/fayos [0] | IoannisKtenidis/DataAnalysis-Scripts [0] |
| 6 | kumaGoro95/ExpensesApp [1] | mjuenema/python-TSIP [0] | tomosuke-chiba/kou-ai-training-sandbox [0] |
| 7 | shu0115/receibo [2] | hankliu62/rc-footer [0] | S-H-GAMELINKS/MyFirstRails [0] |
| 8 | kaku3/workbooks [0] | cbbing/stock [0] | tetezi/workspaceAdmin [0] |
| 9 | paraccoli/flutter_finance_app [2] | imarshio/imarshio.github.io [0] | qlitre/django-mdb-kakeibo [2] |
| 10 | feel7jp/memo_ai [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | facooya/fayos [0] |

### n06-zh-notes (non_english)

> 开源的笔记应用，支持 markdown

nDCG@10: Keyword (today) n/a, Archive only n/a, Hybrid n/a
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | VolhaBakanouskaya/GitHubDaily-public [0] | ChivenZhang/OpenUI [0] | VolhaBakanouskaya/GitHubDaily-public [0] |
| 2 | dike3120/-- [0] | imarshio/imarshio.github.io [0] | ChivenZhang/OpenUI [0] |
| 3 | sftfjugg/GitHubDaily [0] | tetezi/workspaceAdmin [0] | dike3120/-- [0] |
| 4 | happyhappyvip/GitHub_Web [0] | hankliu62/rc-footer [0] | imarshio/imarshio.github.io [0] |
| 5 | zengzebin-wlxs/awesome-linux-software-zh_cn [0] | ybwdaisy/react-native-youzan [0] | sftfjugg/GitHubDaily [0] |
| 6 |  | lmw0726/SpringSource [0] | tetezi/workspaceAdmin [0] |
| 7 |  | yelog/layui-soul-table [0] | happyhappyvip/GitHub_Web [0] |
| 8 |  | poohlaha/rust-tools [0] | hankliu62/rc-footer [0] |
| 9 |  | blanktao/blanktao.github.io [0] | ybwdaisy/react-native-youzan [0] |
| 10 |  | mathsgod/markdown-splitter [0] | zengzebin-wlxs/awesome-linux-software-zh_cn [0] |

### n07-hi-weather (non_english)

> मौसम की जानकारी दिखाने वाला ऐप

nDCG@10: Keyword (today) n/a, Archive only n/a, Hybrid n/a
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | aparif786-web/Muqaddas-Global-API-Framework [0] | kawmra/Owl-Timekeeper [0] | kawmra/Owl-Timekeeper [0] |
| 2 |  | HjRu94/revello [0] | aparif786-web/Muqaddas-Global-API-Framework [0] |
| 3 |  | cykret99/GanttChart [0] | HjRu94/revello [0] |
| 4 |  | XiaWei-NEU/XiaWei-NEU.github.io [0] | cykret99/GanttChart [0] |
| 5 |  | zsu58/zsu58.github.io [0] | XiaWei-NEU/XiaWei-NEU.github.io [0] |
| 6 |  | eyecatchup/MyCountdown-app [0] | zsu58/zsu58.github.io [0] |
| 7 |  | gael-vanderlee/gael-vanderlee.github.io [0] | eyecatchup/MyCountdown-app [0] |
| 8 |  | enbrea/enbrea.konsoli [0] | gael-vanderlee/gael-vanderlee.github.io [0] |
| 9 |  | rik-banerjee-git/demo-movie-recom [0] | enbrea/enbrea.konsoli [0] |
| 10 |  | ondras/wwwsqldesigner [0] | rik-banerjee-git/demo-movie-recom [0] |

### n08-kn-dictionary (non_english)

> ಕನ್ನಡ ಇಂಗ್ಲಿಷ್ ನಿಘಂಟು ಆಪ್

nDCG@10: Keyword (today) n/a, Archive only n/a, Hybrid n/a
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 |  | anhoder/anhoder [0] | anhoder/anhoder [0] |
| 2 |  | HjRu94/revello [0] | HjRu94/revello [0] |
| 3 |  | zsu58/zsu58.github.io [0] | zsu58/zsu58.github.io [0] |
| 4 |  | eyecatchup/MyCountdown-app [0] | eyecatchup/MyCountdown-app [0] |
| 5 |  | JRZhang2003/JRZhang2003.github.io [0] | JRZhang2003/JRZhang2003.github.io [0] |
| 6 |  | CDEBase/cdm-logger [0] | CDEBase/cdm-logger [0] |
| 7 |  | duereg/no-cliches [0] | duereg/no-cliches [0] |
| 8 |  | enbrea/enbrea.konsoli [0] | enbrea/enbrea.konsoli [0] |
| 9 |  | XiaWei-NEU/XiaWei-NEU.github.io [0] | XiaWei-NEU/XiaWei-NEU.github.io [0] |
| 10 |  | rik-banerjee-git/demo-movie-recom [0] | rik-banerjee-git/demo-movie-recom [0] |

### x01-time-travel (no_match)

> send emails to my past self twenty years ago

nDCG@10: Keyword (today) n/a, Archive only n/a, Hybrid n/a
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | awesome-selfhosted/awesome-selfhosted [0] | gael-vanderlee/gael-vanderlee.github.io [0] | awesome-selfhosted/awesome-selfhosted [0] |
| 2 | SamPutnam/Index-2026 [0] | IoannisKtenidis/Task-Automation-Tool [0] | gael-vanderlee/gael-vanderlee.github.io [0] |
| 3 | bbatsov/clojure-style-guide [0] | theabbie/Doodle-Board [0] | SamPutnam/Index-2026 [0] |
| 4 | pdfernhout/High-Performance-Organizations-Reading-List [0] | GalaxiMaster/wordini [0] | IoannisKtenidis/Task-Automation-Tool [0] |
| 5 | Dylan-Israel/ultimate-coding-resources [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | bbatsov/clojure-style-guide [0] |
| 6 | charlax/engineering-management [0] | Fernando-Sousa-Leal/github-slideshow [0] | theabbie/Doodle-Board [0] |
| 7 | famstack-dev/famstack [0] | SamSaffron/blog [0] | pdfernhout/High-Performance-Organizations-Reading-List [0] |
| 8 | profullstack/agenticjobs [0] | HjRu94/revello [0] | GalaxiMaster/wordini [0] |
| 9 | amitshekhariitbhu/ai-system-design [0] | Cyborgscode/Personal-Voice-Assistent [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |
| 10 | RongleCat/awesome-grok-bot [0] | ip2location/ip2location-ruby [0] | Dylan-Israel/ultimate-coding-resources [0] |

### x02-gibberish (no_match)

> zqxv plorbnik wexterflum

nDCG@10: Keyword (today) n/a, Archive only n/a, Hybrid n/a
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 |  | AAGI-AUS/qcflow-rnaseq [0] | AAGI-AUS/qcflow-rnaseq [0] |
| 2 |  | Cyborgscode/Personal-Voice-Assistent [0] | Cyborgscode/Personal-Voice-Assistent [0] |
| 3 |  | theabbie/Doodle-Board [0] | theabbie/Doodle-Board [0] |
| 4 |  | MeadCo/ScriptX.Print.Client [0] | MeadCo/ScriptX.Print.Client [0] |
| 5 |  | tilia/tilia-xml [0] | tilia/tilia-xml [0] |
| 6 |  | cwchentw/shlibs [0] | cwchentw/shlibs [0] |
| 7 |  | gael-vanderlee/gael-vanderlee.github.io [0] | gael-vanderlee/gael-vanderlee.github.io [0] |
| 8 |  | salrashid123/golang-jwt-pqc [0] | salrashid123/golang-jwt-pqc [0] |
| 9 |  | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |
| 10 |  | curvefi/curve-xdao [0] | curvefi/curve-xdao [0] |

### x03-cat-translator (no_match)

> translate what my cat is thinking into full english sentences with perfect accuracy

nDCG@10: Keyword (today) n/a, Archive only n/a, Hybrid n/a
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | Felix3322/PotPlayer_ChatGPT_Translate [0] | mljar/enrichment [0] | Felix3322/PotPlayer_ChatGPT_Translate [0] |
| 2 | Neywa-Labs/mlx-vlm [0] | happytianhao/TOP [0] | mljar/enrichment [0] |
| 3 | rullerzhou-afk/clawd-on-desk [0] | kseo/brainfuck [0] | Neywa-Labs/mlx-vlm [0] |
| 4 | awesome-dsh-plugin/awesome-dsh-plugin [0] | theabbie/Doodle-Board [0] | happytianhao/TOP [0] |
| 5 | J0o1ey/BountyHunterInChina [0] | HjRu94/revello [0] | kseo/brainfuck [0] |
| 6 | MadAppGang/claudish [0] | eyecatchup/MyCountdown-app [0] | rullerzhou-afk/clawd-on-desk [0] |
| 7 | jwasham/coding-interview-university [0] | robenkleene/parrot [0] | theabbie/Doodle-Board [0] |
| 8 | Gear61/Software-Project-Ideas [0] | matt-FFFFFF/matt-FFFFFF [0] | awesome-dsh-plugin/awesome-dsh-plugin [0] |
| 9 | fenxer/llm-things [0] | duereg/adverb-where [0] | J0o1ey/BountyHunterInChina [0] |
| 10 | jondot/rust-how-do-i-start [0] | TridotsTech/go1_meet [0] | HjRu94/revello [0] |

### x04-lottery (no_match)

> guaranteed way to predict the winning lottery numbers

nDCG@10: Keyword (today) n/a, Archive only n/a, Hybrid n/a
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | MinghuiChen43/awesome-deep-phenomena [0] | ggould256/bisector [0] | ggould256/bisector [0] |
| 2 | Callam7/LottoPipeline [0] | ciphergoth/pylambdac [0] | MinghuiChen43/awesome-deep-phenomena [0] |
| 3 | lechmazur/step_game [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | ciphergoth/pylambdac [0] |
| 4 | imsky/PocketEuler [0] | mgb45/MoGapFill [0] | Callam7/LottoPipeline [0] |
| 5 | mrz1836/go-lucky [0] | qepting91/streamlitransomware [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |
| 6 | evanzd/ICLR2021-OpenReviewData [0] | NOAA-ORR-ERD/lat_lon_parser [0] | lechmazur/step_game [0] |
| 7 | AI-Efficiency/Awesome-Model-Quantization [0] | mathsgod/markdown-splitter [0] | imsky/PocketEuler [0] |
| 8 | curia007/lottery [0] | HjRu94/revello [0] | mgb45/MoGapFill [0] |
| 9 | jacobptrk-sudo/lottochamp-official [0] | happytianhao/TOP [0] | qepting91/streamlitransomware [0] |
| 10 | Lottoexposed/lottochamp-official [0] | dario-pilori/capacity-functions [0] | mrz1836/go-lucky [0] |

### x05-emoji-only (no_match)

> 🦄🍕🚀

nDCG@10: Keyword (today) n/a, Archive only n/a, Hybrid n/a
Status: Keyword (today) query_not_supported, Archive only ok, Hybrid degraded

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 |  | HjRu94/revello [0] | HjRu94/revello [0] |
| 2 |  | anhoder/anhoder [0] | anhoder/anhoder [0] |
| 3 |  | mathsgod/markdown-splitter [0] | mathsgod/markdown-splitter [0] |
| 4 |  | lmw0726/SpringSource [0] | lmw0726/SpringSource [0] |
| 5 |  | theabbie/Doodle-Board [0] | theabbie/Doodle-Board [0] |
| 6 |  | happytianhao/TOP [0] | happytianhao/TOP [0] |
| 7 |  | XiaWei-NEU/XiaWei-NEU.github.io [0] | XiaWei-NEU/XiaWei-NEU.github.io [0] |
| 8 |  | TridotsTech/go1_meet [0] | TridotsTech/go1_meet [0] |
| 9 |  | u17g/u17g.com [0] | u17g/u17g.com [0] |
| 10 |  | imarshio/imarshio.github.io [0] | imarshio/imarshio.github.io [0] |

### v01-vague-productive (vague)

> something to help me be more productive

nDCG@10: Keyword (today) 0.431, Archive only 0.000, Hybrid 0.333
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | VGraupera/1on1-questions [0] | theabbie/Doodle-Board [0] | VGraupera/1on1-questions [0] |
| 2 | medplum/medplum [0] | mathsgod/markdown-splitter [0] | theabbie/Doodle-Board [0] |
| 3 | dabeaz-course/practical-python [0] | needcaffeine/dotfiles [0] | medplum/medplum [0] |
| 4 | super-productivity/super-productivity [2] | beyondcode/helo-laravel [0] | mathsgod/markdown-splitter [0] |
| 5 | ardanlabs/gotraining [0] | GalaxiMaster/wordini [0] | needcaffeine/dotfiles [0] |
| 6 | bobbyiliev/introduction-to-bash-scripting [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | dabeaz-course/practical-python [0] |
| 7 | ashishps1/awesome-behavioral-interviews [0] | tausani-ah-chong/tausani-portfolio [0] | super-productivity/super-productivity [2] |
| 8 | trptcolin/reply [0] | gael-vanderlee/gael-vanderlee.github.io [0] | beyondcode/helo-laravel [0] |
| 9 | petehunt/react-howto [0] | ab-prog1/ab-prog1 [0] | ardanlabs/gotraining [0] |
| 10 | ksindi/managers-playbook [0] | eska-muc/dbvisualizer [0] | GalaxiMaster/wordini [0] |

### v02-vague-learn (vague)

> help me learn things faster

nDCG@10: Keyword (today) 0.564, Archive only 0.000, Hybrid 0.307
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | matloff/fasteR [0] | GalaxiMaster/wordini [0] | matloff/fasteR [0] |
| 2 | mtdvio/every-programmer-should-know [1] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] | GalaxiMaster/wordini [0] |
| 3 | jamiebuilds/itsy-bitsy-data-structures [0] | sarsko/CreuSAT [0] | mtdvio/every-programmer-should-know [1] |
| 4 | bobbyiliev/introduction-to-bash-scripting [0] | HjRu94/revello [0] | ignacio-chiazzo/Algorithms-Leetcode-Javascript [0] |
| 5 | jordansissel/fpm [0] | Fernando-Sousa-Leal/github-slideshow [0] | jamiebuilds/itsy-bitsy-data-structures [0] |
| 6 | iam-veeramalla/Docker-Zero-to-Hero [0] | u17g/u17g.com [0] | sarsko/CreuSAT [0] |
| 7 | kando-menu/kando [0] | mathsgod/markdown-splitter [0] | bobbyiliev/introduction-to-bash-scripting [0] |
| 8 | vuejs/awesome-vue [0] | gael-vanderlee/gael-vanderlee.github.io [0] | HjRu94/revello [0] |
| 9 | LockerProject/Locker [0] | theabbie/Doodle-Board [0] | jordansissel/fpm [0] |
| 10 | charlax/professional-programming [1] | SamSaffron/blog [0] | Fernando-Sousa-Leal/github-slideshow [0] |

### v03-long-sentence (vague)

> I want to build something where people in my neighbourhood can lend each other tools like drills and ladders, see who has what, and book a time to pick it up

nDCG@10: Keyword (today) n/a, Archive only n/a, Hybrid n/a
Status: Keyword (today) ok, Archive only ok, Hybrid ok

| # | Keyword (today) | Archive only | Hybrid |
| --- | --- | --- | --- |
| 1 | pelias/pelias [0] | theabbie/Doodle-Board [0] | pelias/pelias [0] |
| 2 | alyssaxuu/mapus [0] | nycynik/dotFiles [0] | theabbie/Doodle-Board [0] |
| 3 | whosonfirst/whosonfirst-placetypes [0] | tilia/tilia-event [0] | nycynik/dotFiles [0] |
| 4 | breferrari/obsidian-mind [0] | tilia/tilia-http [0] | alyssaxuu/mapus [0] |
| 5 | AleksNeStu/ai-real-estate-assistant [0] | tilia/tilia-vobject [0] | whosonfirst/whosonfirst-placetypes [0] |
| 6 | Kenton-GMI/sakura-crossing [0] | tilia/tilia-uri [0] | tilia/tilia-event [0] |
| 7 | ta-data-lis/Project-Week-2-Lisbon [0] | tilia/tilia-xml [0] | tilia/tilia-http [0] |
| 8 | radumas/bikeways4everybody [0] | kseo/brainfuck [0] | breferrari/obsidian-mind [0] |
| 9 | jreades/urb-studies-predicting-gentrification [0] | ab-prog1/ab-prog1 [0] | tilia/tilia-vobject [0] |
| 10 | traghav/auto-redteam [0] | HjRu94/revello [0] | AleksNeStu/ai-real-estate-assistant [0] |
