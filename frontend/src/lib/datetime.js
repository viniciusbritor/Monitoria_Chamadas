/**
 * Helper centralizado para formatacao de datas em GMT-3 (Brasil/Sao_Paulo).
 * Mirror do /Coherence_Portal/frontend/src/lib/datetime.js para consistencia.
 * NEW (08/07/2026 - Alinhamento GMT-3).
 */

const BRT_FORMATTER = new Intl.DateTimeFormat('pt-BR', {
  timeZone: 'America/Sao_Paulo',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

const BRT_DATETIME_FORMATTER = new Intl.DateTimeFormat('pt-BR', {
  timeZone: 'America/Sao_Paulo',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

export function fmtDateBR(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '-';
  return BRT_FORMATTER.format(d);
}

export function fmtDateTimeBR(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '-';
  return BRT_DATETIME_FORMATTER.format(d);
}