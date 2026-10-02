# Architecture diagram styling

Use a minimal neutral palette, matching the surrounding GitHub theme. Avoid saturated or nearly black node fills that obscure labels. Theme backgrounds and labels must be updated together.

| Role | Light | Dark |
| --- | --- | --- |
| Canvas | #FFFFFF | #0D1117 |
| Nodes | #F6F8FA | #161B22 |
| Borders | #D0D7DE | #30363D |
| Main labels | #24292F | #E6EDF3 |
| Secondary labels and arrows | #57606A | #8B949E |

Keep clear arrowheads, generous spacing, short labels, and a readable flow. Use color only when it conveys meaning; this diagram needs no additional accent colors. Provide descriptive alternative text and preserve the distinction between planned and implemented components.

README.md uses GitHub's light/dark image fragments to select matching SVG variants. The Mermaid source is preserved in architecture.mmd. When changing the architecture, update that source and both SVG variants together and visually inspect both. Do not change data flow merely to restyle the diagram.
