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
    {
      name: "ai/release",
      channel: "alpha",
      prerelease: "alpha",
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
           * Issue-reference trailers (Fixes/Closes #N) join the notes;
           * other footer lines stay out — BREAKING CHANGE gets its own
           * section through noteGroups.
           */
          commitPartial(_context, commit) {
            let line = commit.header || "";
            if (commit.body) {
              line += `\n\n${commit.body}`;
            }
            const refs = String(commit.footer || "")
              .split("\n")
              .map((l) => l.trim())
              .filter((l) =>
                /^(fixes|fixed|closes|closed|resolves|resolved|ref|refs)\s+#[0-9]+/i.test(
                  l,
                ),
              );
            if (refs.length) {
              line += `\n\n${refs.join("\n")}`;
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
      {
        assets: ["dist/*.zip"],
        // main -> status:released; rc/dev -> status:released-<channel>
        releasedLabels: [
          "status:released<%= nextRelease.channel ? '-' + nextRelease.channel : '' %>",
        ],
      },
    ],
  ],
};
