export type Annotation = {
    name: string;
    func_x: number;
    ofs_x: number;
    ofs_y: number;
}
export type AnnLeg = {
    name: string;
    annotations: Annotation[];
};