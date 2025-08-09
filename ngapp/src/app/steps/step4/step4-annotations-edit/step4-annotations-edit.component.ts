import { AfterViewInit, Component, OnDestroy, ViewChild } from '@angular/core';
import { Router } from '@angular/router';
import { MatIconModule } from "@angular/material/icon";
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { Subscription } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';

import { ImageEditService } from '../../../services/image-edit.service';
import { MapEditComponent } from "../../../components/mapedit/map-edit/map-edit.component";
import { HeaderComponent } from '../../../components/header/header/header.component';
import { AnnLeg, Annotation } from '../../../models/annotations'
import { MathEditComponent } from '../../../components/mathedit/math-edit/math-edit.component';

@Component({
    selector: 'app-step4-annotations-edit',
    standalone: true,
    imports: [
        CommonModule,
        MatIconModule,
        FlexLayoutModule,
        FormsModule,
        MatCheckboxModule,
        MatButtonModule,
        MapEditComponent,
        MathEditComponent,
        HeaderComponent,
    ],
    templateUrl: './step4-annotations-edit.component.html',
    styleUrl: './step4-annotations-edit.component.css'
})
export class Step4AnnotationsEditComponent implements AfterViewInit, OnDestroy {

    private readonly numPieces: number = 100;

    subs: Subscription;

    legs: AnnLeg[] = [];
    leg_index: number = 0;
    leg_func: (x: number) => number = (x) => x;
    leg_matrix: number[][] = [];
    leg_invmatrix: number[][] = [];
    leg_points: { x: number, y: number }[] = [];
    private _showBubbles: boolean = false;
    set showBubbles(value: boolean) {
        this._showBubbles = value;
        this.mapedit.drawOverlayTransformed();
    }
    get showBubbles() {
        return this._showBubbles;
    }
    
    @ViewChild(MapEditComponent) mapedit!: MapEditComponent;
    @ViewChild(MathEditComponent) mathedit!: MathEditComponent;

    constructor(public router: Router, private imgsrv: ImageEditService) {
        this.subs = imgsrv.channel.subscribe((msg) => {
            if (msg.type === "annotations") {
                if (msg['svg_overlay'] && msg['svg_overlay']!=='-') {
                    this.mapedit.setSVG(msg['svg_overlay']);
                }
                this.legs = msg['annotations'].map((leg: any) => {
                    return {
                        name: leg.name,
                        function_latex: leg.function_name,
                        function_mathjs_compiled: this.mathedit.getMathJS(this.mathedit.getAST(leg.function_name)).compile(),
                        matrix_func2cropmap: leg.matrix_func2cropmap,
                        matrix_cropmap2func: leg.matrix_cropmap2func,
                        annotations: leg.annotations.map((ann: any) => {
                            return {
                                name: ann.name,
                                func_x: ann.func_x,
                                ofs_x: ann.ofs.x,
                                ofs_y: ann.ofs.y,
                            }
                        }),
                    }
                });
                this.changeLeg(0);
            }
        });
    }

    ngAfterViewInit(): void {
        // initiate image load
        this.imgsrv.send({ type: 'get-annotations' });
        this.imgsrv.send({ type: 'get-annotations-map' });
    }

    ngOnDestroy(): void {
        // stop observers
        this.subs.unsubscribe();
    }

    changeLeg(increment: number) {
        let new_index = this.leg_index + increment;
        if (new_index >= this.legs.length) new_index = 0;
        if (new_index < 0) new_index = this.legs.length - 1;
        if (new_index >= 0 && new_index < this.legs.length) {
            this.leg_index = new_index;
            this.leg_func = (x: number) => this.legs[this.leg_index].function_mathjs_compiled?.evaluate({ x: x });
            this.leg_matrix = this.legs[this.leg_index].matrix_func2cropmap;
            this.leg_invmatrix = this.legs[this.leg_index].matrix_cropmap2func;
            this.calculateFuncPoints();
        }
        this.mapedit.drawOverlayTransformed();
    }

    updateAnnotations() {
        this.imgsrv.send({
            type: 'update-annotations',
            annotations: this.legs.map((leg: AnnLeg) => {
                return {
                    name: leg.name,
                    annotations: leg.annotations.map((ann: Annotation) => {
                        return {
                            name: ann.name,
                            func_x: ann.func_x,
                            ofs: {x: ann.ofs_x, y: ann.ofs_y},
                        }
                    })
                }
            }),
        });
    }
    

    deleteAnnotation(index: number) {
        this.legs[this.leg_index].annotations.splice(index, 1);
        this.updateAnnotations();
    }

    enumPoints(enumerate: (i: number, x: number, y: number) => boolean) {
        for (var i = 1; i < this.legs[this.leg_index].annotations.length - 1; i++) {
            // we don't enumerate the first and last (because those are edited in the previous step)
            const ann = this.legs[this.leg_index].annotations[i];
            const mappt = this.applyTransformationMatrix({ x: ann.func_x, y: this.leg_func(ann.func_x) }, this.leg_matrix);
            if (!enumerate(i, mappt.x, mappt.y)) {
                break;
            }
        }
    }

    movePointTo(event: { i: number, x: number, y: number, callback: () => void }) {
        // calculate function point closest to x,y
        const { index: minidx, point: minpt, point_func: minptfunc } = this.calcMinimumPoint(event);
        const x = minptfunc.x;
        // check if still between the point before and after
        const prev_x = this.legs[this.leg_index].annotations[event.i - 1].func_x;
        const next_x = this.legs[this.leg_index].annotations[event.i + 1].func_x;
        if ((x > prev_x && x < next_x) || (x > next_x && x < prev_x)) {
            // change point
            this.legs[this.leg_index].annotations[event.i].func_x = x;
            event.callback();
        }
    }

    finalizeMove() {
        this.updateAnnotations();
    }

    addPointAt(event: { x: number, y: number, callback: () => void }) {
        const anns = this.legs[this.leg_index].annotations;
        // calculate function point closest to x,y
        const { index: minidx, point: minpt, point_func: minptfunc } = this.calcMinimumPoint(event);
        const x = minptfunc.x;
        // find the two neighbours (i.e. the index)
        let index = anns.length - 1;
        for (let i = 0; i < anns.length - 1; i++) {
            const prev_x = anns[i].func_x;
            const next_x = anns[i + 1].func_x;
            if ((x > prev_x && x < next_x) || (x > next_x && x < prev_x)) {
                index = i + 1;
                break;
            }
        }
        // insert new annotation
        anns.splice(index, 0, {
            name: 'xxx',
            func_x: x,
            ofs_x: 0,
            ofs_y: 0,
        });
        event.callback();
        // send to server
        this.updateAnnotations();
    }

    change(prop: string, index: number, event: any) {
        if (!event.target) return;
        let target = (event.target as HTMLInputElement);
        if (!target.value) return;
        const ann = this.legs[this.leg_index].annotations[index];
        if (prop == "name") {
            const val: string = target.value;
            ann[prop] = val;    
        } else if (prop=="func_x" || prop=="ofs_x" || prop=="ofs_y") {
            const val: number = parseFloat(target.value);
            ann[prop] = val;
        }
        this.updateAnnotations();
        this.mapedit.drawOverlayTransformed();
    }

    private calculateFuncPoints() {
        this.leg_points = [];
        let last_x = this.legs[this.leg_index].annotations[0].func_x;
        for (let i = 1; i < this.legs[this.leg_index].annotations.length; i++) {
            const ann = this.legs[this.leg_index].annotations[i]
            for (let k = 0; k <= this.numPieces; k++) {
                const dx = k * (ann.func_x - last_x) / this.numPieces;
                const funcpt = { x: last_x + dx, y: this.leg_func(last_x + dx) };
                const mappt = this.applyTransformationMatrix(funcpt, this.leg_matrix);
                this.leg_points.push(mappt);
            }
        }
    }

    private calcMinimumPoint(p: { x: number, y: number }): { index: number; point: { x: number; y: number }; point_func: { x: number; y: number } } {
        // calculate function point closest to p=(x,y)
        const minidx = this.leg_points.map((pt) => {
            const [xp, yp] = [pt.x, pt.y]; //this.mapedit.getImage2CanvasCoords(pt.x, pt.y);
            const dist = Math.sqrt((xp - p.x) ** 2 + (yp - p.y) ** 2);
            return dist
        }).reduce((mnidx, cur, i, a) => {
            if (mnidx == -1 || cur <= a[mnidx]) {
                return i;
            } else {
                return mnidx;
            }
        }, -1);
        const minpt = this.leg_points[minidx];
        const minptfunc = this.applyTransformationMatrix(minpt, this.leg_invmatrix);
        return { index: minidx, point: minpt, point_func: minptfunc };
    }

    drawOverlayTransformed(event: { canvas: HTMLCanvasElement, imgWidth: number, imgHeight: number }) {
        // get references and clear canvas
        const canvas = event.canvas;
        const ctx = canvas.getContext('2d')!;
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        for (var j = 0; j < 2; j++) { // to have the selected leg drawn last
            for (var l = 0; l < this.legs.length; l++) {
                //let func = (x: number) => x**(1/3); // fixed to linear f(x)=x
                let func = (x: number) => this.legs[l].function_mathjs_compiled?.evaluate({ x: x });

                const leg = this.legs[l];
                if ((leg.annotations.length > 0) && ((j == 0) != (this.leg_index == l))) {
                    const ann = leg.annotations;
                    // draw polygon
                    let last_x = ann[0].func_x;
                    const mappt = this.applyTransformationMatrix({ x: ann[0].func_x, y: func(ann[0].func_x) }, leg.matrix_func2cropmap);
                    const [x, y] = this.mapedit.getImage2CanvasCoords(mappt.x, mappt.y);
                    ctx.beginPath();
                    ctx.moveTo(x, y);
                    for (let i = 1; i < ann.length; i++) {
                        for (let k = 0; k <= this.numPieces; k++) {
                            const dx = k * (ann[i].func_x - last_x) / this.numPieces;
                            const funcpt = { x: last_x + dx, y: func(last_x + dx) };
                            const mappt = this.applyTransformationMatrix(funcpt, leg.matrix_func2cropmap);
                            const [x, y] = this.mapedit.getImage2CanvasCoords(mappt.x, mappt.y);
                            ctx.lineTo(x, y);
                        }
                        last_x = ann[i].func_x;
                    }
                    //ctx.closePath();
                    ctx.lineWidth = 6;
                    ctx.strokeStyle = l == this.leg_index ? "red" : "blue";
                    ctx.stroke();

                    // draw points and bubbles
                    for (let i = 0; i < ann.length; i++) {
                        const mappt = this.applyTransformationMatrix({ x: ann[i].func_x, y: func(ann[i].func_x) }, leg.matrix_func2cropmap);
                        const [x, y] = this.mapedit.getImage2CanvasCoords(mappt.x, mappt.y);
                        ctx.beginPath();
                        ctx.fillStyle = (l == this.leg_index) ? (i == this.mapedit.selectedPoint) ? "green" : "red" : "blue";
                        ctx.arc(x, y, 12, 0, 2 * Math.PI);
                        ctx.fill();
                        if (this._showBubbles) {
                            const tmapx = mappt.x + ann[i].ofs_x * this.mapedit.dpi / 72;
                            const tmapy = mappt.y - ann[i].ofs_y * this.mapedit.dpi / 72;
                            const scale = this.mapedit.getScale();
                            const scale_display = {
                                x: scale.x * 4,
                                y: scale.y * 4
                            };
                            ctx.font = "12px serif";
                            const bubsize = this.estimateBubbleSize(10, (i == 0) ? 2 : 4, 30);
                            const bubsize_scaled = {
                                width: bubsize.width * scale_display.x,
                                height: bubsize.height * scale_display.y
                            };
                            const [tx, ty] = this.mapedit.getImage2CanvasCoords(tmapx, tmapy)
                            //const [tx, ty] = [x + ann[i].ofs_x, y - ann[i].ofs_y];
                            this.drawBubble(
                                ctx,
                                tx, ty - bubsize_scaled.height / 2,
                                bubsize_scaled.width, bubsize_scaled.height,
                                ann[i].name,
                                12 * scale_display.x
                            );
                        }
                    }

                }
            }
        }
    }


    private estimateBubbleSize(fontSize: number, numLines: number, maxChars: number): { width: number; height: number } {
        const charWidth = 0.58 * fontSize;      // average char width
        const lineHeight = 1.2 * fontSize;     // line spacing
        const padding = 0.5 * fontSize;        // bubble margin

        const width = maxChars * charWidth + 2 * padding;
        const height = numLines * lineHeight + 2 * padding;

        return { width, height };
    }

    private drawBubble(
        ctx: CanvasRenderingContext2D,
        x: number,
        y: number,
        width: number,
        height: number,
        text: string,
        fontSize: number = 14
    ) {
        ctx.save(); // save state

        // Bubble background
        ctx.fillStyle = "rgba(135, 206, 250, 0.5)"; // semi-transparent lightblue
        ctx.strokeStyle = "rgba(0, 0, 0, 0.8)";     // darker border
        ctx.lineWidth = 2;

        this.drawRoundedRect(ctx, x, y, width, height, 3);
        ctx.fill();
        ctx.stroke();

        // Draw text
        ctx.fillStyle = "black";
        ctx.font = `${fontSize}px sans-serif`;
        ctx.textAlign = "left";
        ctx.textBaseline = "top";

        const lines = text.split("\n");
        const lineHeight = fontSize * 1.2;
        for (let i = 0; i < lines.length; i++) {
            ctx.fillText(lines[i], x + 10, y + 10 + i * lineHeight);
        }

        ctx.restore(); // restore state
    }

    private drawRoundedRect(
        ctx: CanvasRenderingContext2D,
        x: number,
        y: number,
        width: number,
        height: number,
        radius: number
    ) {
        ctx.beginPath();
        ctx.moveTo(x + radius, y);
        ctx.lineTo(x + width - radius, y);
        ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
        ctx.lineTo(x + width, y + height - radius);
        ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
        ctx.lineTo(x + radius, y + height);
        ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
        ctx.lineTo(x, y + radius);
        ctx.quadraticCurveTo(x, y, x + radius, y);
        ctx.closePath();
    }


    /**
     * Apply a 2D transformation matrix to a point.
     * @param {{x: number, y: number}} point - Original point.
     * @param {number[][]} matrix - 3x3 transformation matrix as nested arrays.
     * @returns {{x: number, y: number}} Transformed point.
     */
    private applyTransformationMatrix(point: { x: number, y: number }, matrix: number[][]) {
        // Convert point to homogeneous coordinates vector
        const pointVector = [point.x, point.y, 1];

        // Multiply matrix * pointVector
        const transformedVector = [
            matrix[0][0] * pointVector[0] + matrix[0][1] * pointVector[1] + matrix[0][2] * pointVector[2],
            matrix[1][0] * pointVector[0] + matrix[1][1] * pointVector[1] + matrix[1][2] * pointVector[2],
            matrix[2][0] * pointVector[0] + matrix[2][1] * pointVector[1] + matrix[2][2] * pointVector[2],
        ];

        // Return the transformed point (ignore the homogeneous coordinate w)
        return { x: transformedVector[0], y: transformedVector[1] };
    }

}
