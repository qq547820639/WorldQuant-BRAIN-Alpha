export function reportIgnoredError(context: string, error: unknown): void {
  if (process.env.NODE_ENV === "development") {
    console.debug(context, error);
  }
}
