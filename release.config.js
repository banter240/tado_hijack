export default {
  branches: [
    "main",
    {
      name: "rc",
      channel: "rc",
      prerelease: "rc",
    },
    {
      name: "dev",
      channel: "dev",
      prerelease: "dev",
    },
  ],
  plugins: [
    [
      "@semantic-release/commit-analyzer",
      { preset: "conventionalcommits" },
    ],
    [
      "@semantic-release/release-notes-generator",
      {
        preset: "conventionalcommits",
        presetConfig: {
          types: [
            { type: "feat", section: "✨ New Features" },
            { type: "fix", section: "🐛 Bug Fixes" },
            { type: "perf", section: "⚡ Performance Improvements" },
            { type: "revert", section: "Reverts", effect: "hidden" },
            { type: "docs", section: "📚 Documentation", effect: "changelog" },
            { type: "style", section: "Styles", effect: "hidden" },
            { type: "chore", section: "Miscellaneous", effect: "hidden" },
            { type: "refactor", section: "Code Refactoring", effect: "hidden" },
            { type: "test", section: "Tests", effect: "hidden" },
            { type: "build", section: "Build System", effect: "hidden" },
            { type: "ci", section: "Continuous Integration", effect: "hidden" },
          ],
        },
        writerOpts: {
          /**
           * conventional-changelog-writer v9 replaced Handlebars strings with
           * render functions. list() already prepends "* ", so return inner text.
           */
          commitPartial(_context, commit) {
            let line = commit.header || "";
            if (commit.body) {
              line += `\n\n${commit.body}`;
            }
            return line;
          },
        },
      },
    ],
    [
      "@semantic-release/exec",
      { prepareCmd: "./scripts/publish.sh ${nextRelease.version}" },
    ],
    "@semantic-release/changelog",
    [
      "@semantic-release/git",
      {
        message:
          "chore(release): 🚀 publish version ${nextRelease.version}\n\n${nextRelease.notes}\n\n[skip ci]",
        assets: [
          "CHANGELOG.md",
          "custom_components/tado_hijack/manifest.json",
        ],
      },
    ],
    [
      "@semantic-release/github",
      { assets: ["dist/*.zip"] },
    ],
  ],
};
