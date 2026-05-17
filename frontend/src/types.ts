export interface Label { id: number; name: string; color: string; }
export interface Project { name: string; labels: Label[]; sources: unknown[]; }
export interface CaseSummary {
  id: string;
  kind: "aligned" | "raw_dicom";
  modalities: string[];
  annotated: boolean;
  labels_present: string[];
}
export interface CaseDetail {
  id: string;
  kind: "aligned" | "raw_dicom";
  modalities: string[];
  slice_count: number;
  reference_shape: [number, number, number];
  reference_affine: number[][];
  modality_files: Record<string, string[]>;
}
export interface MaskEnvelope {
  shape: [number, number, number];
  dtype: "uint8";
  data: string; // base64
  warnings?: string[];
}
