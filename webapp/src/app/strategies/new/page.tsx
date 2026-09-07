"use client";

import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { PageHeader, PageBody } from "@/components/layout/PageHeader";
import { StrategyBuilder } from "@/components/strategy/StrategyBuilder";
import { emptyDraft } from "@/lib/strategy-draft";
import { api, ApiError } from "@/lib/api-client";
import type { StrategyDefinition } from "@/lib/types";

export default function NewStrategyPage() {
  const router = useRouter();

  const mutation = useMutation({
    mutationFn: (definition: StrategyDefinition) => api.createStrategy(definition),
    onSuccess: (created) => router.push(`/strategies/${created.id}`),
  });

  return (
    <>
      <PageHeader title="New strategy" breadcrumb="strategies / new" />
      <PageBody className="max-w-3xl">
        <StrategyBuilder
          initialDraft={emptyDraft()}
          submitLabel="Create strategy"
          submitting={mutation.isPending}
          submitError={mutation.error instanceof ApiError ? mutation.error.message : mutation.error ? "Something went wrong." : null}
          onSubmit={(definition) => mutation.mutate(definition)}
        />
      </PageBody>
    </>
  );
}
