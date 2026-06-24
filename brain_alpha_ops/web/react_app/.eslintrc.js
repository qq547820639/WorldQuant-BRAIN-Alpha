module.exports = {
  root: true,
  env: {
    browser: true,
    es2020: true,
    node: true,
  },
  extends: [
    "eslint:recommended",
    "plugin:react/recommended",
    "plugin:react-hooks/recommended",
    "plugin:jsx-a11y/recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:@typescript-eslint/recommended-requiring-type-checking",
  ],
  parser: "@typescript-eslint/parser",
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
    ecmaFeatures: {
      jsx: true,
    },
  },
  plugins: [
    "react",
    "react-hooks",
    "jsx-a11y",
    "@typescript-eslint",
  ],
  rules: {
    // React rules
    "react/react-in-jsx-scope": "off",
    "react/prop-types": "off",
    "react/display-name": "off",

    // React Hooks rules
    "react-hooks/rules-of-hooks": "error",
    "react-hooks/exhaustive-deps": "warn",

    // TypeScript rules
    "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
    "@typescript-eslint/no-explicit-any": "warn",
    "@typescript-eslint/explicit-module-boundary-types": "off",
    "@typescript-eslint/no-non-null-assertion": "off",

    // JSX Accessibility rules
    "jsx-a11y/alt-text": "warn",
    "jsx-a11y/anchor-has-content": "warn",
    "jsx-a11y/aria-props": "warn",
    "jsx-a11y/aria-proptypes": "warn",
    "jsx-a11y/aria-unsupported-elements": "warn",
    "jsx-a11y/click-events-have-key-events": "warn",
    "jsx-a11y/heading-has-content": "warn",
    "jsx-a11y/html-has-lang": "warn",
    "jsx-a11y/img-redundant-alt": "warn",
    "jsx-a11y/interactive-supports-focus": "warn",
    "jsx-a11y/label-has-associated-control": "warn",
    "jsx-a11y/mouse-events-have-key-events": "warn",
    "jsx-a11y/no-autofocus": "warn",
    "jsx-a11y/no-distracting-elements": "warn",
    "jsx-a11y/no-noninteractive-element-interactions": "warn",
    "jsx-a11y/no-static-element-interactions": "warn",
    "jsx-a11y/role-has-required-aria-props": "warn",
    "jsx-a11y/role-supports-aria-props": "warn",
    "jsx-a11y/scope": "warn",
    "jsx-a11y/tabindex-no-positive": "warn",

    // General rules
    "no-console": ["warn", { allow: ["warn", "error"] }],
    "no-debugger": "warn",
  },
  settings: {
    react: {
      version: "detect",
    },
  },
  overrides: [
    {
      files: ["*.test.ts", "*.test.tsx", "*.spec.ts", "*.spec.tsx"],
      rules: {
        "@typescript-eslint/no-explicit-any": "off",
        "@typescript-eslint/no-non-null-assertion": "off",
      },
    },
  ],
};
