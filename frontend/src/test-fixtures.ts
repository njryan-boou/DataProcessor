import type { DatasetMetadata } from './types'
export const dataset: DatasetMetadata = {
  id: 'dataset-id', filename: 'team.csv', file_size: 1024, rows: 123, column_count: 3,
  missing_values: 4, duplicate_rows: 3, version: 1, history: [],
  columns: [{ name:'name',type:'text',missing:1,unique:118 },{ name:'age',type:'numeric',missing:3,unique:45 },{ name:'salary',type:'numeric',missing:0,unique:87 }],
}
