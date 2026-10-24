import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';

const expoRequire = createRequire(require.resolve('expo/package.json'));
const cliPath = expoRequire.resolve('@expo/cli/package.json');
const cliRequire = createRequire(cliPath);
const { z } = cliRequire('zod') as typeof import('zod');
const schemasPath = resolve(dirname(cliPath), 'build/src/start/server');
const { PluginSchema, DevToolsPluginOutputSchema } = cliRequire(
  resolve(schemasPath, 'DevToolsPlugin.schema.js')
);
const { createMCPDevToolsExtensionSchema } = cliRequire(
  resolve(schemasPath, 'createMCPDevToolsExtensionSchema.js')
);

const plugin = {
  packageName: 'test-plugin',
  packageRoot: '/test/plugin',
  cliExtensions: {
    description: 'Test commands',
    entryPoint: './commands.js',
    commands: [{
      name: 'inspect',
      title: 'Inspect a project',
      environments: ['cli', 'mcp'],
      parameters: [
        { name: 'target', type: 'text' },
        { name: 'count', type: 'number' },
        { name: 'confirmed', type: 'confirm' },
      ],
    }],
  },
};

test('Expo resolves a validator that rejects oversized bounded arrays before walking elements', () => {
  const result = z.array(z.string()).max(100).safeParse(Array(1000).fill(0));
  expect(result.success).toBe(false);
  if (result.success) throw new Error('Oversized input was accepted');
  expect(result.error.issues).toHaveLength(1);
  expect(result.error.issues[0].code).toBe('too_big');
});

test('Expo plugin metadata and output schemas retain valid and invalid behavior', () => {
  expect(PluginSchema.parse(plugin)).toEqual(plugin);
  expect(PluginSchema.safeParse({ ...plugin, packageName: '' }).success).toBe(false);
  expect(PluginSchema.safeParse({ ...plugin, cliExtensions: {
    ...plugin.cliExtensions, commands: [],
  } }).success).toBe(false);
  const output = [{ type: 'text', text: 'Ready', level: 'info' }];
  expect(DevToolsPluginOutputSchema.parse(output)).toEqual(output);
  expect(DevToolsPluginOutputSchema.safeParse([{ type: 'unknown' }]).success).toBe(false);
});

test('Expo MCP command schemas keep typed parameters and reject unknown commands or keys', () => {
  const schema = createMCPDevToolsExtensionSchema(plugin);
  const input = { command: 'inspect', target: 'repo', count: 2, confirmed: true };
  expect(schema.parse(input)).toEqual(input);
  expect(schema.safeParse({ command: 'missing' }).success).toBe(false);
  expect(schema.safeParse({ command: 'inspect', count: 'two' }).success).toBe(false);
  expect(schema.safeParse({ command: 'inspect', extra: true }).success).toBe(false);
});
