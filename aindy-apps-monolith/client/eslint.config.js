import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs['recommended-latest'],
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    rules: {
      'no-unused-vars': ['error', { varsIgnorePattern: '^[A-Z_]' }],
      'no-restricted-syntax': [
        'error',
        {
          selector: "CallExpression[callee.type='MemberExpression'][callee.property.name='map']",
          message: 'Use safeMap(...) instead of direct .map(...) calls.',
        },
        {
          selector: "OptionalCallExpression[callee.type='OptionalMemberExpression'][callee.property.name='map']",
          message: 'Use safeMap(...) instead of direct .map(...) calls.',
        },
      ],
    },
  },
  {
    files: ['src/utils/safe.js'],
    rules: {
      'no-restricted-syntax': 'off',
    },
  },
])
