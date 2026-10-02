module.exports = {
  collectCoverageFrom: ['src/**/*.{ts,tsx}'],
  coverageReporters: ['text', 'json-summary', 'lcov'],
  coverageThreshold: require('../.ci/quality-policy.json').mobile_coverage,
  preset: 'jest-expo',
  testMatch: ['**/tests/**/*.test.ts?(x)'],
  setupFilesAfterEnv: ['<rootDir>/tests/setup.ts'],
};
