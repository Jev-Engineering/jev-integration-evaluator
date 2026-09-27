// Parsed with the trusted TypeScript compiler, never this repository's Node plugins.
interface LLM { choose(state: unknown): Promise<string>; }
interface Executor { execute_tool(action: string): Promise<{success: boolean}>; }
export async function opaqueSeam(llm: LLM, executor: Executor, state: unknown) {
  const proposed = await llm.choose(state);
  const result = await executor.execute_tool(proposed);
  return result.success;
}
export const exactScale = (n: number): number => n * 100;
