export type Annotation = {
    name: string;
    func_x: number;
    ofs_x: number;
    ofs_y: number;
}
export type AnnLeg = {
    name: string;
    function_latex: string;
    function_mathjs_compiled: any;
    matrix_func2cropmap: number[][];
    matrix_cropmap2func: number[][];
    annotations: Annotation[];
};