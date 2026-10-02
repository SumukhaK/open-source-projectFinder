const { defineConfig } = require('eslint/config');
const expo = require('eslint-config-expo/flat');
module.exports = defineConfig([
  expo,
  { ignores: ['dist/**', 'coverage/**', 'node_modules/**'] },
  { files: ['src/**/*.{ts,tsx}'], rules: {
    'import/no-restricted-paths': ['error', { zones: [
      { target: './src/features', from: './src/app' },
      { target: ['./src/components', './src/hooks', './src/lib', './src/config'], from: ['./src/features', './src/app'] },
    ] }],
  } },
]);
