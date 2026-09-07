import type { ConditionNode, Operand } from "./types";

function describeOperand(o: Operand): string {
  return typeof o === "number" ? String(o) : o;
}

const OP_SYMBOLS: Record<string, string> = {
  gt: ">",
  gte: ">=",
  lt: "<",
  lte: "<=",
  eq: "==",
  ne: "!=",
  crosses_above: "crosses above",
  crosses_below: "crosses below",
};

export function describeCondition(node: ConditionNode): string {
  if (node.type === "comparison") {
    return `${describeOperand(node.left)} ${OP_SYMBOLS[node.op] ?? node.op} ${describeOperand(node.right)}`;
  }
  const inner = node.conditions.map((c) => (c.type === "comparison" ? describeCondition(c) : `(${describeCondition(c)})`));
  return inner.join(` ${node.op.toUpperCase()} `);
}
