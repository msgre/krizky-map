// Překlad kanonické konfigurace z docs/guidelines/javascript.md (.eslintrc.json) do flat configu ESLint 9+.
import js from '@eslint/js';
import globals from 'globals';

export default [
  { ignores: ['node_modules/', 'dist/', '**/*.min.js', '.claude/', '.venv/'] },
  js.configs.recommended,
  {
    files: ['**/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: { ...globals.browser },
    },
    rules: {
      'no-var': 'error',
      'prefer-const': 'error',
      'prefer-arrow-callback': 'error',
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      eqeqeq: ['error', 'always'],
      curly: ['error', 'all'],
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-implicit-globals': 'error',
      'prefer-template': 'warn',
      'object-shorthand': ['warn', 'always'],
    },
  },
  {
    files: ['**/*.test.mjs', 'eslint.config.mjs'],
    languageOptions: { sourceType: 'module', globals: { ...globals.node } },
  },
];
