export function demoEnabled(): boolean {
  return process.env.ENABLE_DEMO_MODE === "true" &&
    ["development", "local", "test"].includes((process.env.APP_ENV ?? "").toLowerCase()) &&
    !["production", "preview", "staging"].some(value =>
      [process.env.VERCEL_ENV, process.env.DEPLOYMENT_ENV, process.env.ENVIRONMENT]
        .some(environment => environment?.toLowerCase() === value));
}
