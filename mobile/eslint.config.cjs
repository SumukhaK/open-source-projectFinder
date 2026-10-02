const { defineConfig } = require('eslint/config');
const security = require('eslint-plugin-security');
const expo = require('eslint-config-expo/flat');
module.exports = defineConfig([
  expo,
  { files: ['src/**/*.{ts,tsx}'], plugins: { security }, rules: Object.fromEntries(Object.keys(security.configs.recommended.rules).map(rule => [rule, 'error'])) },
  { ignores: ['dist/**', 'coverage/**', 'node_modules/**'] },
  { files: ['src/**/*.{ts,tsx}'], rules: {
    'import/no-restricted-paths': ['error', { zones: [
      { target: './src/features', from: './src/app' },
      { target: ['./src/components', './src/hooks', './src/lib', './src/config'], from: ['./src/features', './src/app'] },
    ] }],
  } },
]);
