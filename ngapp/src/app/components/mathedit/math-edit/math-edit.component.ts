import { AfterViewInit, Component, CUSTOM_ELEMENTS_SCHEMA, ElementRef, EventEmitter, Output, ViewChild } from '@angular/core';
import 'mathlive';
import { ComputeEngine } from '@cortex-js/compute-engine';
import { create, all, MathNode } from 'mathjs';
import { MathfieldElement } from 'mathlive';

const math = create(all);

@Component({
    selector: 'app-math-edit',
    standalone: true,
    imports: [],
    schemas: [CUSTOM_ELEMENTS_SCHEMA],
    templateUrl: './math-edit.component.html',
    styleUrl: './math-edit.component.css'
})
export class MathEditComponent implements AfterViewInit {
    @ViewChild('mf') mf!: ElementRef;
    @Output() latexChange = new EventEmitter<{ latex: string, ast: any, mathjs: any }>();

    private ce!: ComputeEngine;
    
    ngAfterViewInit(): void {
        this.ce = new ComputeEngine();
        MathfieldElement.computeEngine = this.ce;
    }

    onInput(event: any) {
        const latex = this.getLatex();
        const ast = this.getAST(latex);
        if (!ast) return;
        const mathjs = this.getMathJS(ast);
        if (!mathjs) return;
        this.latexChange.emit({
            latex: latex,
            ast: ast,
            mathjs: mathjs,
        });
    }

    setLatex(latex: string) {
        this.mf.nativeElement.setValue(latex);
    }

    getLatex() {
        return this.mf.nativeElement.getValue();
    }

    getAST(latex: string) {
        try {
            return this.ce.parse(latex).json;
        } catch (e) {
            return null;
        }
    }

    getMathJS(ast: any) {
        let mathjs: any;
        try {
            mathjs = mathjsonToMathjs(ast);
        } catch (e) {
            mathjs = null;
        }
        return mathjs;
    }

}

function mathjsonToMathjs(node: any): any {
    // Base case: number or symbol
    if (typeof node === 'number') return math.parse(node.toString());
    if (typeof node === 'string') {
        if (node == 'ExponentialE') {
            return math.parse('e');
        } else {
            return math.parse(node);
        }
    }

    // Object form: { fn: "Add", args: [...] }
    if (node && typeof node === 'object' && !Array.isArray(node)) {
        const fn = node.fn;
        const args = (node.args || []).map(mathjsonToMathjs);
        return applyFn(fn, args);
    }

    // Array form: ["Add", arg1, arg2, ...]
    if (Array.isArray(node)) {
        const fn = node[0];
        const args = node.slice(1).map(mathjsonToMathjs);
        return applyFn(fn, args);
    }

    throw new Error(`Invalid MathJSON node: ${JSON.stringify(node)}`);
}

function applyFn(fn: string, args: MathNode[]): MathNode {
    switch (fn) {
        case 'Add': return new math.OperatorNode('+', 'add', args);
        case 'Subtract': return new math.OperatorNode('-', 'subtract', args);
        case 'Multiply': return new math.OperatorNode('*', 'multiply', args);
        case 'Divide': return new math.OperatorNode('/', 'divide', args);
        case 'Power': return new math.OperatorNode('^', 'pow', args);
        case 'Negate': return new math.OperatorNode('-', 'unaryMinus', args);
        case 'Root':
            args[1] = new math.OperatorNode('/', 'divide', [new math.ConstantNode(1), args[1]]);
            return new math.OperatorNode('^', 'pow', args);
        case 'Sin': return new math.FunctionNode('sin', args);
        case 'Cos': return new math.FunctionNode('cos', args);
        case 'Tan': return new math.FunctionNode('tan', args);
        case 'Exp': return new math.FunctionNode('exp', args);
        case 'Ln': return new math.FunctionNode('log', args);
        default: throw new Error(`Unsupported fn: ${fn}`);
    }
}


