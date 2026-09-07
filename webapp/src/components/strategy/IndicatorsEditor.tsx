"use client";

import { INDICATOR_CATALOG, indicatorSpecByName } from "@/lib/indicator-catalog";
import { defaultIndicatorDraft, IndicatorDraft, suggestAlias } from "@/lib/strategy-draft";
import { Button } from "@/components/ui/Button";
import { Label, NumberInput, Select, TextInput } from "@/components/ui/Field";

export function IndicatorsEditor({
  indicators,
  onChange,
}: {
  indicators: IndicatorDraft[];
  onChange: (next: IndicatorDraft[]) => void;
}) {
  function addIndicator() {
    const first = INDICATOR_CATALOG[0];
    const alias = suggestAlias(first.name, indicators.map((i) => i.alias));
    onChange([...indicators, defaultIndicatorDraft(first.name, alias)]);
  }

  function updateIndicator(id: string, patch: Partial<IndicatorDraft>) {
    onChange(indicators.map((i) => (i.id === id ? { ...i, ...patch } : i)));
  }

  function changeIndicatorType(id: string, name: string) {
    const alias = suggestAlias(name, indicators.filter((i) => i.id !== id).map((i) => i.alias));
    const replacement = { ...defaultIndicatorDraft(name, alias), id };
    onChange(indicators.map((i) => (i.id === id ? replacement : i)));
  }

  function removeIndicator(id: string) {
    onChange(indicators.filter((i) => i.id !== id));
  }

  return (
    <div className="space-y-3">
      {indicators.length === 0 && (
        <p className="text-sm text-[var(--text-muted)] border border-dashed border-[var(--border-strong)] rounded-[var(--radius-md)] px-4 py-6 text-center">
          No indicators yet. You can still reference raw OHLCV columns (close, volume, ...) in conditions, or add one below.
        </p>
      )}

      {indicators.map((ind) => {
        const spec = indicatorSpecByName(ind.name);
        return (
          <div key={ind.id} className="border border-[var(--border)] rounded-[var(--radius-md)] p-4 bg-[var(--bg)]">
            <div className="flex items-end gap-3 mb-3">
              <div className="flex-1">
                <Label>Indicator</Label>
                <Select value={ind.name} onChange={(e) => changeIndicatorType(ind.id, e.target.value)}>
                  {INDICATOR_CATALOG.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="flex-1">
                <Label hint="used in conditions">Alias</Label>
                <TextInput
                  value={ind.alias}
                  onChange={(e) => updateIndicator(ind.id, { alias: e.target.value })}
                  className="font-mono"
                />
              </div>
              <Button variant="ghost" onClick={() => removeIndicator(ind.id)} aria-label="Remove indicator">
                Remove
              </Button>
            </div>

            {spec && spec.params.length > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {spec.params.map((paramSpec) => {
                  const current = ind.params[paramSpec.name] ?? { mode: "fixed", value: paramSpec.defaultValue };
                  return (
                    <div key={paramSpec.name} className="border border-[var(--border)] rounded-[var(--radius-sm)] p-2.5">
                      <div className="flex items-center justify-between mb-1.5">
                        <Label>{paramSpec.label}</Label>
                        <button
                          type="button"
                          onClick={() =>
                            updateIndicator(ind.id, {
                              params: {
                                ...ind.params,
                                [paramSpec.name]:
                                  current.mode === "fixed"
                                    ? { mode: "range", default: current.value, min: paramSpec.min, max: paramSpec.max, step: paramSpec.step }
                                    : { mode: "fixed", value: current.default },
                              },
                            })
                          }
                          className="text-[10px] uppercase tracking-wide text-[var(--accent)] hover:text-[var(--accent-strong)] font-mono"
                        >
                          {current.mode === "fixed" ? "make range" : "make fixed"}
                        </button>
                      </div>
                      {current.mode === "fixed" ? (
                        <NumberInput
                          value={current.value}
                          step="any"
                          onChange={(e) =>
                            updateIndicator(ind.id, {
                              params: { ...ind.params, [paramSpec.name]: { mode: "fixed", value: Number(e.target.value) } },
                            })
                          }
                        />
                      ) : (
                        <div className="grid grid-cols-3 gap-1.5">
                          <NumberInput
                            aria-label="min"
                            value={current.min}
                            step="any"
                            onChange={(e) =>
                              updateIndicator(ind.id, { params: { ...ind.params, [paramSpec.name]: { ...current, min: Number(e.target.value) } } })
                            }
                          />
                          <NumberInput
                            aria-label="default"
                            value={current.default}
                            step="any"
                            onChange={(e) =>
                              updateIndicator(ind.id, {
                                params: { ...ind.params, [paramSpec.name]: { ...current, default: Number(e.target.value) } },
                              })
                            }
                          />
                          <NumberInput
                            aria-label="max"
                            value={current.max}
                            step="any"
                            onChange={(e) =>
                              updateIndicator(ind.id, { params: { ...ind.params, [paramSpec.name]: { ...current, max: Number(e.target.value) } } })
                            }
                          />
                        </div>
                      )}
                      {current.mode === "range" && (
                        <div className="grid grid-cols-3 gap-1.5 mt-1 text-[10px] text-[var(--text-faint)] text-center">
                          <span>min</span>
                          <span>default</span>
                          <span>max</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}

      <Button variant="secondary" type="button" onClick={addIndicator}>
        + Add indicator
      </Button>
    </div>
  );
}
