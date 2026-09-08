import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import type { Root } from 'postcss';
export default defineConfig({
  plugins: [react()],
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  css: { postcss: { plugins: [{
    postcssPlugin: 'streamlit-control-scope',
    OnceExit(root: Root) {
      root.walkRules(rule => {
        let parent: typeof rule.parent | Root['parent'] = rule.parent;
        while (parent) {
          if (parent.type === 'atrule' && /keyframes$/i.test(parent.name)) return;
          parent = parent.parent;
        }
        rule.selectors = rule.selectors.map(selector => selector.includes('.oj-component')
          ? selector : selector.includes(':root') ? selector.replaceAll(':root', '.oj-component')
          : `.oj-component ${selector}`);
      });
    },
  }] } },
  build: {
    outDir: "../tmp/streamlit-build",
    emptyOutDir: true,
    lib: { entry: resolve("streamlit/entry.tsx"), formats: ["es"], fileName: () => "oj-components.js", cssFileName: "oj-components" },
    rolldownOptions: { output: { codeSplitting: false } },
  },
});
