# RepoRadar: Project Scope

RepoRadar will help people discover whether an open-source project already addresses their idea. A person describes what they want to build by typing or speaking into a mobile app. The service searches public GitHub projects and returns similar repositories.

It will combine a periodically refreshed collection of repository information with GitHub search. This aims to find projects with related purposes even when their names use different words.

The initial scope is idea submission and discovery of similar public repositories. Detailed screens, result presentation, and additional features will be defined during brainstorming. A match does not prove that an idea is unique, that a repository is suitable, or that its code is ready to reuse.

Current progress: the mobile branding/sign-in foundation and backend authentication, public GitHub repository details and account-specific favourites are implemented. The feature branch also adds controls for how many search results to request and how to sort them, with validation and safety tests; final review and delivery checks remain pending. Semantic matching, combining search sources and repository ingestion remain planned.

## Account access

Users sign up or log in with a single GitHub button. RepoRadar does not request private repository access. The app saves its own secure session; GitHub credentials stay on the backend. Signing out ends that app session. Authentication is implemented and automatically tested, while live GitHub and device validation need the app's OAuth setup. Discovery and voice remain future features.

## Quality before new features

Every change is automatically tested and checked for code/security issues before review and merging. The checks use free tools and need no additional account keys. The app can recover from a screen-rendering failure, and the backend records safe local crash events. Production crash monitoring and deployment remain future work. GitHub's included runner allowance still limits hosted automation.
