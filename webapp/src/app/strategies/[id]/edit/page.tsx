"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { PageHeader, PageBody } from "@/components/layout/PageHeader";
import { StrategyBuilder } from "@/components/strategy/StrategyBuilder";
import { definitionToDraft } from "@/lib/strategy-draft";
import { api, ApiError } from "@/lib/api-client";
import type { StrategyDefinition } from "@/lib/types";
import { LoadingPanel, ErrorBanner } from "@/components/ui/EmptyState";

export default function EditStrategyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();

  const { data: strategy, isLoading, error } = useQuery({
    queryKey: ["strategy", id],
    queryFn: () => api.getStrategy(id),
  });

  const mutation = useMutation({
    mutationFn: (definition: StrategyDefinition) => api.updateStrategy(id, definition),
    onSuccess: () => router.push(`/strategies/${id}`),
  });

  return (
    <>
      <PageHeader title="Edit strategy" breadcrumb={`strategies / ${id} / edit`} />
      <PageBody className="max-w-3xl">
        {isLoading && <LoadingPanel />}
        {error && <ErrorBanner message={error instanceof ApiError ? error.message : "Could not load this strategy."} />}
        {strategy && (
          <StrategyBuilderForStrategy
            definition={strategy.definition}
            onSubmit={(definition) => mutation.mutate(definition)}
            submitting={mutation.isPending}
            submitError={mutation.error instanceof ApiError ? mutation.error.message : mutation.error ? "Something went wrong." : null}
          />
        )}
      </PageBody>
    </>
  );
}

function StrategyBuilderForStrategy({
  definition,
  onSubmit,
  submitting,
  submitError,
}: {
  definition: StrategyDefinition;
  onSubmit: (definition: StrategyDefinition) => void;
  submitting: boolean;
  submitError: string | null;
}) {
  const parsed = definitionToDraft(definition);
  const warnings = [
    ...(parsed.unsupportedEntry ? ["entry"] : []),
    ...(parsed.unsupportedExit ? ["exit"] : []),
  ];
  return (
    <StrategyBuilder
      initialDraft={parsed.draft}
      parseWarnings={warnings}
      submitLabel="Save changes"
      submitting={submitting}
      submitError={submitError}
      onSubmit={onSubmit}
    />
  );
}
