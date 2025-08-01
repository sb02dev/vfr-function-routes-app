export type LegPoint = {
    x: number;
    y: number;
    lon: number;
    lat: number;
    func_x: number;
    lonlat_valid: boolean
}
export type Leg = {
    name: string;
    function_latex: string;
    function_mathjs_compiled: any;
    function_range: string;
    matrix_func2cropmap: number[][];
    matrix_cropmap2func: number[][];
    points: LegPoint[];
};