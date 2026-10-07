"use client";

import { Button } from "@/components/ui/button";

interface PaginationControlsProps {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  previousLabel: string;
  nextLabel: string;
  summaryLabel: string;
  pageSizeLabel: string;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

export function PaginationControls({
  page,
  pageSize,
  total,
  totalPages,
  previousLabel,
  nextLabel,
  summaryLabel,
  pageSizeLabel,
  onPageChange,
  onPageSizeChange,
}: PaginationControlsProps) {
  if (total === 0) return null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t p-3 text-sm">
      <span>{summaryLabel}</span>
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-2">
          {pageSizeLabel}
          <select
            aria-label={pageSizeLabel}
            className="h-9 rounded-md border bg-background px-2"
            value={pageSize}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
          >
            {[10, 20, 50].map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
        <Button
          disabled={page <= 1}
          size="sm"
          variant="outline"
          onClick={() => onPageChange(page - 1)}
        >
          {previousLabel}
        </Button>
        <Button
          disabled={totalPages === 0 || page >= totalPages}
          size="sm"
          variant="outline"
          onClick={() => onPageChange(page + 1)}
        >
          {nextLabel}
        </Button>
      </div>
    </div>
  );
}
