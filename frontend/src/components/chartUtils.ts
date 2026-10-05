import type { ChartKind, DatasetMetadata } from '../types';

type Column = DatasetMetadata['columns'][number];

export interface ChartSelection {
  x: string;
  y: string;
}

export function validColumns(
  columns: Column[],
  kind: ChartKind,
  axis: 'x' | 'y',
): Column[] {
  if (axis === 'y') {
    return kind === 'histogram' || kind === 'box'
      ? []
      : columns.filter((column) => column.type === 'numeric');
  }
  if (kind === 'bar') {
    return columns.filter((column) => column.type === 'text' || column.type === 'boolean');
  }
  if (kind === 'line') {
    return columns.filter((column) => column.type === 'numeric' || column.type === 'datetime');
  }
  return columns.filter((column) => column.type === 'numeric');
}

export function validSelection(
  columns: Column[],
  kind: ChartKind,
  current: ChartSelection = { x: '', y: '' },
): ChartSelection {
  const xColumns = validColumns(columns, kind, 'x');
  const yColumns = validColumns(columns, kind, 'y');
  const x = xColumns.some((column) => column.name === current.x)
    ? current.x
    : xColumns[0]?.name ?? '';
  const y = kind === 'bar' && current.y === ''
    ? ''
    : yColumns.some((column) => column.name === current.y)
      ? current.y
      : (yColumns.find((column) => column.name !== x) ?? yColumns[0])?.name ?? '';
  return { x, y };
}

export function chartCanGenerate(kind: ChartKind, selection: ChartSelection): boolean {
  return Boolean(selection.x && ((kind !== 'line' && kind !== 'scatter') || selection.y));
}
