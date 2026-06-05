type IntegrationField = {
  label: string;
  value: string;
};

type IntegrationSectionProps = {
  title: string;
  error: string | null;
  installedFields: IntegrationField[] | null;
  notConnectedMessage: string;
  installUrl?: string | null;
  installLabel?: string;
  secondaryUrl?: string | null;
  secondaryLabel?: string;
};

export function IntegrationSection({
  title,
  error,
  installedFields,
  notConnectedMessage,
  installUrl,
  installLabel,
  secondaryUrl,
  secondaryLabel,
}: IntegrationSectionProps) {
  return (
    <section className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <h2 className="text-sm font-medium text-zinc-950 dark:text-zinc-50">{title}</h2>
      {error ? (
        <p className="mt-2 text-sm text-red-600">{error}</p>
      ) : installedFields ? (
        <dl className="mt-3 space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
          <div>
            <dt className="font-medium text-zinc-950 dark:text-zinc-50">Status</dt>
            <dd>Installed</dd>
          </div>
          {installedFields.map((field) => (
            <div key={field.label}>
              <dt className="font-medium text-zinc-950 dark:text-zinc-50">{field.label}</dt>
              <dd className="font-mono text-xs break-all">{field.value}</dd>
            </div>
          ))}
        </dl>
      ) : installUrl && installLabel ? (
        <>
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{notConnectedMessage}</p>
          <div className="mt-4 flex flex-col gap-2 sm:flex-row">
            <a
              href={installUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex h-10 items-center justify-center rounded-full bg-zinc-950 px-4 text-sm font-medium text-white transition-colors hover:bg-zinc-800 dark:bg-zinc-50 dark:text-zinc-950 dark:hover:bg-zinc-200"
            >
              {installLabel}
            </a>
            {secondaryUrl && secondaryLabel ? (
              <a
                href={secondaryUrl}
                className="inline-flex h-10 items-center justify-center rounded-full border border-zinc-200 px-4 text-sm font-medium text-zinc-950 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-50 dark:hover:bg-zinc-900"
              >
                {secondaryLabel}
              </a>
            ) : null}
          </div>
        </>
      ) : (
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{notConnectedMessage}</p>
      )}
    </section>
  );
}
