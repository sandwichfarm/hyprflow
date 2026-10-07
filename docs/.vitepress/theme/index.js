import { h } from "vue";
import DefaultTheme from "vitepress/theme";
import "../../../website/shared/palette.css";
import "./style.css";
export default {
  extends: DefaultTheme,
  Layout: () =>
    h(DefaultTheme.Layout, null, {
      "nav-bar-content-after": () =>
        h("a", { href: "/", class: "website-link" }, "Website ↗"),
    }),
};
