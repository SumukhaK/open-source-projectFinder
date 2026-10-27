# RepoRadar: Project Scope

RepoRadar will help people discover whether an open-source project already addresses their idea. A person describes what they want to build by typing or speaking into a mobile app. The service searches public GitHub projects and returns similar repositories.

It will combine a periodically refreshed collection of repository information with GitHub search. This aims to find projects with related purposes even when their names use different words.

The initial scope is idea submission and discovery of similar public repositories. Detailed screens, result presentation, and additional features will be defined during brainstorming. A match does not prove that an idea is unique, that a repository is suitable, or that its code is ready to reuse.

Current progress: the mobile branding/sign-in foundation and backend authentication, public GitHub repository details and account-specific favourites are implemented. Search also supports controls for how many results to request and how to sort them, with validation and safety tests. Review, automated checks and delivery are recorded in [PR #10](https://github.com/SumukhaK/open-source-projectFinder/pull/10). Semantic matching, combining search sources and repository ingestion remain planned.

## Account access

Users sign up or log in with a single GitHub button. RepoRadar does not request private repository access. The app saves its own secure session; GitHub credentials stay on the backend. Signing out ends that app session. Authentication is implemented and automatically tested, while live GitHub and device validation need the app's OAuth setup. Mobile discovery screens and voice remain future features.

## Quality before new features

Every change is automatically tested and checked for code/security issues before review and merging. The checks use free tools and need no additional account keys. The app can recover from a screen-rendering failure, and the backend records safe local crash events. Production crash monitoring and deployment remain future work. GitHub's included runner allowance still limits hosted automation.

A small local database feasibility experiment now proves CPU and GPU operations on 1,000 synthetic vectors. GPU 1k proof passed; archive capacity remains open. A separate archive catalogue and a compatible SQLite runtime are now tested and merged in T03. It does not ingest GitHub projects or implement hybrid search; weekly archive operation remains planned. This experiment and the component that turns text into searchable vectors have both been reviewed and merged.


The T03 change adds a private local filing catalogue for repository records and content revisions, separate from account data. It has been tested with synthetic records on this laptop and merged via PR #18. It does not download GitHub projects, refresh them weekly or change the app's search results. Those remain later tasks.

T05 prepares small, repeatable text sections from supplied repository descriptions and README content, with clear limits and notices when content is left out. It has been reviewed and merged via PR #20. This preparation runs locally without downloading repository content and does not yet add projects to the search index or change search results.

T06 stores the bounded README bytes and prepared sections in a private local archive, together with provenance such as source hashes and versions. It is merged. It does not download repositories, publish them to the search index or change the app's search results.
