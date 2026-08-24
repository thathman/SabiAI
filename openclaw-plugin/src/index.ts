import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { Type } from "typebox";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";

const here = path.dirname(fileURLToPath(import.meta.url));

const configSchema = Type.Object(
  {
    rootDirectory: Type.Optional(
      Type.String({ description: "SabiAI repository/workspace root." }),
    ),
    pythonExecutable: Type.Optional(
      Type.String({ description: "Python executable. Defaults to python3." }),
    ),
  },
  { additionalProperties: false },
);

type PluginConfig = {
  rootDirectory?: string;
  pythonExecutable?: string;
};

type GatewayEnvelope = {
  ok: boolean;
  tool?: string;
  data?: unknown;
  error?: string;
};

function invokePython(
  python: string,
  script: string,
  root: string,
  request: string,
  signal?: AbortSignal,
): Promise<string> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new Error("SabiAI tool call was cancelled."));
      return;
    }
    const child = execFile(
      python,
      [script, "--request", request],
      {
        cwd: root,
        env: process.env,
        encoding: "utf8",
        maxBuffer: 4 * 1024 * 1024,
      },
      (error, stdout, stderr) => {
        if (error) {
          reject(
            new Error(
              `SabiAI V2 gateway failed: ${stderr.trim() || error.message}`,
            ),
          );
          return;
        }
        resolve(stdout);
      },
    );
    if (signal) {
      signal.addEventListener(
        "abort",
        () => {
          child.kill();
        },
        { once: true },
      );
    }
  });
}

async function callGateway(
  toolName: string,
  args: Record<string, unknown>,
  config: PluginConfig,
  signal?: AbortSignal,
): Promise<unknown> {
  const root = path.resolve(
    config.rootDirectory ?? process.env.SABIAI_ROOT ?? path.resolve(here, "..", ".."),
  );
  const python = config.pythonExecutable ?? process.env.SABIAI_PYTHON ?? "python3";
  const script = path.join(root, "scripts", "sabiai_v2_tool.py");
  const request = JSON.stringify({ tool: toolName, args });
  const stdout = await invokePython(python, script, root, request, signal);
  let envelope: GatewayEnvelope;
  try {
    envelope = JSON.parse(stdout) as GatewayEnvelope;
  } catch {
    throw new Error("SabiAI V2 gateway returned invalid JSON.");
  }
  if (!envelope.ok) {
    throw new Error(envelope.error || `SabiAI V2 tool ${toolName} failed.`);
  }
  return envelope.data ?? {};
}

const ticketLeg = Type.Object(
  {
    event_id: Type.Optional(Type.String()),
    home: Type.Optional(Type.String()),
    away: Type.Optional(Type.String()),
    market: Type.Optional(Type.String()),
    pick: Type.Optional(Type.String()),
    odds: Type.Union([Type.String(), Type.Number()]),
    locked: Type.Optional(Type.Boolean()),
    note: Type.Optional(Type.String()),
  },
  { additionalProperties: false },
);

const ruleSchema = Type.Object(
  {
    period: Type.Optional(Type.String()),
    includes_overtime: Type.Optional(Type.Boolean()),
    void_rule: Type.Optional(Type.String()),
    line_key: Type.Optional(Type.String()),
  },
  { additionalProperties: false },
);

const quoteSchema = Type.Object(
  {
    event_key: Type.String(),
    market_key: Type.String(),
    selection_key: Type.String(),
    selection_label: Type.Optional(Type.String()),
    bookmaker: Type.String(),
    odds: Type.Union([Type.String(), Type.Number()]),
    captured_at: Type.Optional(Type.String()),
    rules: Type.Optional(ruleSchema),
  },
  { additionalProperties: false },
);

export default defineToolPlugin({
  id: "sabiai-v2",
  name: "SabiAI V2",
  description:
    "Native OpenClaw tools for Sabi sports research, markets, bookmakers and ticket work.",
  configSchema,
  tools: (tool) => [
    tool({
      name: "sabiai_system_health",
      label: "SabiAI system health",
      description: "Read SabiAI V2 database and domain health.",
      parameters: Type.Object({}, { additionalProperties: false }),
      execute: async (_params, config, context) =>
        callGateway("system.health", {}, config, context.signal),
    }),
    tool({
      name: "sabiai_sports_list",
      label: "SabiAI sports list",
      description:
        "List Sabi's starting sport knowledge registry. The registry is open-ended and is not a support limit.",
      parameters: Type.Object({}, { additionalProperties: false }),
      execute: async (_params, config, context) =>
        callGateway("sports.list", {}, config, context.signal),
    }),
    tool({
      name: "sabiai_sports_describe",
      label: "Describe a sport",
      description:
        "Describe how Sabi currently understands a sport and whether new source/rules discovery is needed.",
      parameters: Type.Object(
        { sport: Type.String({ description: "Sport name, for example volleyball or golf." }) },
        { additionalProperties: false },
      ),
      execute: async (params, config, context) =>
        callGateway("sports.describe", params, config, context.signal),
    }),
    tool({
      name: "sabiai_research_plan",
      label: "Plan sports research",
      description:
        "Create a sport- and market-specific research checklist before Sabi spends source requests.",
      parameters: Type.Object(
        {
          sport: Type.String(),
          market: Type.Optional(Type.String()),
          home: Type.Optional(Type.String()),
          away: Type.Optional(Type.String()),
        },
        { additionalProperties: false },
      ),
      execute: async (params, config, context) =>
        callGateway("research.plan", params, config, context.signal),
    }),
    tool({
      name: "sabiai_market_interpret",
      label: "Interpret a betting market",
      description:
        "Translate bookmaker shorthand into Sabi's clear language with explicit team/player wording.",
      parameters: Type.Object(
        {
          text: Type.String(),
          home: Type.Optional(Type.String()),
          away: Type.Optional(Type.String()),
        },
        { additionalProperties: false },
      ),
      execute: async (params, config, context) =>
        callGateway("market.interpret", params, config, context.signal),
    }),
    tool({
      name: "sabiai_market_arbitrage",
      label: "Check bookmaker prices for arbitrage",
      description:
        "Check a complete normalized market for rule-compatible arbitrage using fresh decimal prices.",
      parameters: Type.Object(
        {
          expected_selections: Type.Array(Type.String(), { minItems: 2 }),
          quotes: Type.Array(quoteSchema, { minItems: 2 }),
          total_stake: Type.Optional(Type.Union([Type.String(), Type.Number()])),
          max_age_seconds: Type.Optional(Type.Integer({ minimum: 0 })),
        },
        { additionalProperties: false },
      ),
      execute: async (params, config, context) =>
        callGateway("market.arbitrage", params, config, context.signal),
    }),
    tool({
      name: "sabiai_bookmaker_resolve",
      label: "Resolve bookmaker name",
      description:
        "Resolve bookmaker names and aliases to Sabi's canonical bookmaker registry.",
      parameters: Type.Object(
        { name: Type.String() },
        { additionalProperties: false },
      ),
      execute: async (params, config, context) =>
        callGateway("bookmaker.resolve", params, config, context.signal),
    }),
    tool({
      name: "sabiai_ticket_split",
      label: "Split a ticket",
      description:
        "Split one normalized ticket into smaller child slips while preserving ticket lineage.",
      parameters: Type.Object(
        {
          bookmaker: Type.Optional(Type.String()),
          source_type: Type.Optional(Type.String()),
          source_reference: Type.Optional(Type.String()),
          slips: Type.Integer({ minimum: 2 }),
          legs: Type.Array(ticketLeg, { minItems: 2 }),
        },
        { additionalProperties: false },
      ),
      execute: async (params, config, context) =>
        callGateway("ticket.split", params, config, context.signal),
    }),
    tool({
      name: "sabiai_ticket_trim",
      label: "Trim a ticket to target odds",
      description:
        "Trim a normalized ticket toward requested combined decimal odds while preserving locked legs.",
      parameters: Type.Object(
        {
          bookmaker: Type.Optional(Type.String()),
          source_type: Type.Optional(Type.String()),
          source_reference: Type.Optional(Type.String()),
          target_odds: Type.Union([Type.String(), Type.Number()]),
          min_legs: Type.Optional(Type.Integer({ minimum: 1 })),
          legs: Type.Array(ticketLeg, { minItems: 1 }),
        },
        { additionalProperties: false },
      ),
      execute: async (params, config, context) =>
        callGateway("ticket.trim", params, config, context.signal),
    }),
  ],
});
