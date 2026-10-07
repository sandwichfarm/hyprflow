import { defineConfig } from "vitepress";
export default defineConfig({
  title: "hyprflow",
  description:
    "Classic Cover Flow for Hyprland workspaces — installation, configuration, and design.",
  base: "/docs/",
  outDir: "../dist/docs",
  appearance: "dark",
  cleanUrls: false,
  head: [
    ["link", { rel: "icon", href: "/docs/favicon.svg", type: "image/svg+xml" }],
    ["meta", { name: "theme-color", content: "#100e0d" }],
  ],
  themeConfig: {
    siteTitle: "hyprflow / docs",
    nav: [{ text: "Get started", link: "/getting-started" }],
    socialLinks: [
      { icon: "github", link: "https://github.com/sandwichfarm/hyprflow" },
    ],
    search: { provider: "local" },
    sidebar: [
      {
        text: "Guide",
        items: [
          { text: "Introduction", link: "/" },
          { text: "Getting started", link: "/getting-started" },
          { text: "Configuration & controls", link: "/configuration" },
          { text: "Troubleshooting", link: "/troubleshooting" },
        ],
      },
      {
        text: "Behind the flow",
        items: [
          { text: "Animation specification", link: "/design-spec" },
          { text: "Reference provenance", link: "/reference/SOURCES" },
          { text: "Acceptance gates", link: "/acceptance" },
          { text: "Verification report", link: "/verification" },
        ],
      },
      {
        text: "Contributing",
        items: [{ text: "Website & deployment", link: "/website" }],
      },
    ],
    editLink: {
      pattern: "https://github.com/sandwichfarm/hyprflow/edit/main/docs/:path",
    },
    footer: {
      message: "Classic Cover Flow for Hyprland workspaces.",
      copyright: "Made by sandwichfarm",
    },
  },
  // Keep source evidence links useful on GitHub and in the rendered docs.
  markdown: {
    config(md) {
      const render = md.renderer.rules.link_open;
      md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
        const href = tokens[idx].attrGet("href");
        if (/^\.\.\/(artifacts\/|config\/|README\.md)/.test(href || "")) {
          tokens[idx].attrSet(
            "href",
            "https://github.com/sandwichfarm/hyprflow/blob/main/" +
              href.slice(3),
          );
        }
        return render
          ? render(tokens, idx, options, env, self)
          : self.renderToken(tokens, idx, options);
      };
    },
  },
});
