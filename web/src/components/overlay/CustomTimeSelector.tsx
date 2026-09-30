import { useMemo } from "react";
import { TimeRange } from "@/types/timeline";
import { useDateLocale } from "@/hooks/use-date-locale";
import { formatSecondsToDuration, getUTCOffset } from "@/utils/dateUtil";
import useSWR from "swr";
import { FrigateConfig } from "@/types/frigateConfig";
import { useTranslation } from "react-i18next";

type CustomTimeSelectorProps = {
  latestTime: number;
  range?: TimeRange;
  setRange: (range: TimeRange | undefined) => void;
  startLabel: string;
  endLabel: string;
};

const pad = (value: number) => value.toString().padStart(2, "0");

// format for <input type="datetime-local">, read from the local clock
function toInputValue(timestamp: number) {
  const date = new Date(timestamp * 1000);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

export function CustomTimeSelector({
  latestTime,
  range,
  setRange,
  startLabel,
  endLabel,
}: CustomTimeSelectorProps) {
  const { t } = useTranslation(["common", "components/dialog"]);
  const locale = useDateLocale();
  const { data: config } = useSWR<FrigateConfig>("config");

  // the inputs edit a clock in the configured UI timezone, but the range
  // always holds real unix timestamps
  const offsetDeltaSeconds = useMemo(() => {
    if (!config?.ui.timezone) {
      return 0;
    }

    const timezoneOffset = Math.round(
      getUTCOffset(new Date(), config.ui.timezone),
    );
    const localTimeOffset = Math.round(
      getUTCOffset(
        new Date(),
        Intl.DateTimeFormat().resolvedOptions().timeZone,
      ),
    );

    return (timezoneOffset - localTimeOffset) * 60;
  }, [config?.ui.timezone]);

  const realStart = range?.after || latestTime - 3600;
  const realEnd = range?.before || latestTime;
  const isInvalid = realEnd <= realStart;

  const onChange = (edge: "after" | "before", value: string) => {
    // cleared or partially typed inputs report an empty value
    if (!value) {
      return;
    }

    const timestamp = new Date(value).getTime() / 1000 - offsetDeltaSeconds;

    if (Number.isNaN(timestamp)) {
      return;
    }

    setRange({
      after: edge === "after" ? timestamp : realStart,
      before: edge === "before" ? timestamp : realEnd,
    });
  };

  const inputClass =
    "w-full rounded-md border border-input bg-background p-2 text-secondary-foreground dark:[color-scheme:dark]";

  return (
    <div className="mt-3 flex flex-col gap-2 rounded-lg bg-secondary p-3 text-secondary-foreground">
      <label className="flex flex-col gap-1 text-sm">
        {startLabel}
        <input
          className={inputClass}
          type="datetime-local"
          step="1"
          aria-label={startLabel}
          value={toInputValue(realStart + offsetDeltaSeconds)}
          onChange={(e) => onChange("after", e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {endLabel}
        <input
          className={inputClass}
          type="datetime-local"
          step="1"
          aria-label={endLabel}
          value={toInputValue(realEnd + offsetDeltaSeconds)}
          onChange={(e) => onChange("before", e.target.value)}
        />
      </label>
      <div
        className={`text-sm ${isInvalid ? "text-danger" : "text-muted-foreground"}`}
      >
        {isInvalid
          ? t("export.toast.error.endTimeMustAfterStartTime", {
              ns: "components/dialog",
            })
          : formatSecondsToDuration(realEnd - realStart, locale)}
      </div>
    </div>
  );
}
