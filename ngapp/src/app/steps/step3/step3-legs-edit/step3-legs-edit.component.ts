import { AfterContentInit, Component, OnDestroy, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from "@angular/material/icon";
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { Subscription } from 'rxjs';
import { Router } from '@angular/router';

import { ImageEditService } from '../../../services/image-edit.service';
import { HeaderComponent } from "../../../components/header/header/header.component";
import { Leg, LegPoint } from '../../../models/leg';
import { MathEditComponent } from "../../../components/mathedit/math-edit/math-edit.component";
import { MapEditComponent } from "../../../components/mapedit/map-edit/map-edit.component";

@Component({
    selector: 'app-step3-legs-edit',
    standalone: true,
    imports: [
        CommonModule,
        MatIconModule,
        MatButtonModule,
        MatTooltipModule,
        FlexLayoutModule,
        MatCardModule,
        MatTableModule,
        MapEditComponent,
        HeaderComponent,
        MathEditComponent
    ],
    templateUrl: './step3-legs-edit.component.html',
    styleUrl: './step3-legs-edit.component.css'
})
export class Step3LegsEditComponent implements AfterContentInit, OnDestroy {
    subs: Subscription;
    @ViewChild(MapEditComponent) mapedit!: MapEditComponent;
    @ViewChild(MathEditComponent) mathedit!: MathEditComponent;

    legs: Leg[] = [];
    leg_index: number = 0;

    extrapoint: [number, number] | null = null;

    constructor(public router: Router, private imgsrv: ImageEditService) {
        this.subs = imgsrv.channel.subscribe((msg) => {
            if (msg.type === "legs") {
                this.legs = msg['legs'].map((leg: any) => {
                    return {
                        name: leg.name,
                        function_latex: leg.function_name,
                        function_mathjs_compiled: this.mathedit.getMathJS(this.mathedit.getAST(leg.function_name)).compile(),
                        function_range: leg.function_range,
                        matrix_func2cropmap: leg.matrix_func2cropmap,
                        matrix_cropmap2func: leg.matrix_cropmap2func,
                        points: leg.points.map((pt: any) => {
                            return {
                                x: pt.x,
                                y: pt.y,
                                lon: pt.lon,
                                lat: pt.lat,
                                func_x: pt.func_x,
                                lonlat_valid: true,
                            }
                        }),
                    }
                });
                this.changeLeg(0);
            }
        });
    }

    ngAfterContentInit(): void {
        // initiate image load
        this.imgsrv.send({ type: 'get-legs' }, ['legs', 'result']);
        this.imgsrv.send({ type: 'get-legs-map' }, ['tiled-image']);
    }

    ngOnDestroy(): void {
        // stop observers
        this.subs.unsubscribe();
    }

    getLatexMarkup() {
        if (!this.legs[this.leg_index])
            return '';
        try {
            return this.mathedit.convertLatexToHTML(this.legs[this.leg_index].function_range);
        } catch {
            return '';
        }
    }

    changeLeg(increment: number) {
        let new_index = this.leg_index + increment;
        if (new_index >= this.legs.length) new_index = 0;
        if (new_index < 0) new_index = this.legs.length - 1;
        if (new_index >= 0 && new_index < this.legs.length) {
            this.leg_index = new_index;
            this.mathedit.setLatex(this.legs[this.leg_index].function_latex);
        }
        this.mapedit.drawOverlayTransformed();
    }

    latexChange($event: { latex: string; ast: any; mathjs: any }) {
        // redraw with the new curve (temporarily)
        const compiled = $event.mathjs.compile();
        this.legs[this.leg_index].function_latex = $event.latex;
        this.legs[this.leg_index].function_mathjs_compiled = compiled;
        this.mapedit.drawOverlayTransformed();
        // send it to the server to recalculate the transformation matrix
        this.updateLegs();
    }

    changeFuncX(index: number, event: any) {
        if (!event.target) return;
        let target = (event.target as HTMLInputElement);
        if (!target.value) return;
        const val: number = parseFloat(target.value);
        this.legs[this.leg_index].points[index].func_x = val;
        this.updateLegs();
    }

    updateLegs() {
        this.imgsrv.send({
            type: 'update-legs',
            legs: this.legs.map((leg: Leg) => {
                return {
                    name: leg.name,
                    function_name: leg.function_latex,
                    function_range: leg.function_range,
                    points: leg.points.map((pt: LegPoint) => {
                        return {
                            x: pt.x,
                            y: pt.y,
                            func_x: pt.func_x,
                        }
                    })
                }
            }),
        }, ['legs', 'result']);
    }

    finalizeMove() {
        this.extrapoint = null;
        this.updateLegs();
    }

    deleteConstraintPoint(index: number) {
        this.legs[this.leg_index].points.splice(index, 1);
        this.updateLegs();
        this.mapedit.drawOverlayTransformed();
    }

    moveConstraintPoint(index: number, up: boolean) {
        let move = up ? -1 : 1;
        this.legs[this.leg_index].points.splice(index + move, 0, this.legs[this.leg_index].points.splice(index, 1)[0]);
        this.updateLegs();
        this.mapedit.drawOverlayTransformed();
    }


    enumPoints(enumerate: (i: number, map_coords: boolean, x: number, y: number, w: number | undefined, h: number | undefined) => boolean) {
        for (var i = 1; i < this.legs[this.leg_index].points.length - 1; i++) {
            // we don't enumerate the first and last (because those are edited in the previous step)
            const lp = this.legs[this.leg_index].points[i];
            if (!enumerate(i, true, lp.x, lp.y, undefined, undefined)) {
                break;
            }
        }
    }

    movePointTo(event: { i: number, x: number, y: number, callback: () => void }) {
        this.legs[this.leg_index].points[event.i].x = event.x;
        this.legs[this.leg_index].points[event.i].y = event.y;
        this.legs[this.leg_index].points[event.i].lonlat_valid = false;
        this.extrapoint = [event.x, event.y];
        event.callback();
    }

    addPointAt(event: { x: number, y: number, callback: () => void }) {
        const pts = this.legs[this.leg_index].points;
        pts.splice(pts.length - 1, 0, {
            x: event.x,
            y: event.y,
            lon: 0,
            lat: 0,
            func_x: 0,
            lonlat_valid: false
        });
        event.callback();
        this.updateLegs();
    }


    compareLegs(index: number, lp: LegPoint) {
        return index;
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
                if ((leg.points.length > 0) && ((j == 0) != (this.leg_index == l))){
                    const pts = leg.points;
                    // draw polygon
                    let last_x = pts[0].func_x;
                    const mappt = this.applyTransformationMatrix({ x: pts[0].func_x, y: func(pts[0].func_x) }, leg.matrix_func2cropmap);
                    const [x, y] = this.mapedit.getImage2CanvasCoords(mappt.x, mappt.y);
                    ctx.beginPath();
                    ctx.moveTo(x, y);
                    const numPieces = 100;
                    for (let i = 1; i < pts.length; i++) {
                        for (let k = 0; k <= numPieces; k++) {
                            const dx = k * (pts[i].func_x - last_x) / numPieces;
                            const funcpt = { x: last_x + dx, y: func(last_x + dx) };
                            const mappt = this.applyTransformationMatrix(funcpt, leg.matrix_func2cropmap);
                            const [x, y] = this.mapedit.getImage2CanvasCoords(mappt.x, mappt.y);
                            ctx.lineTo(x, y);
                        }
                        last_x = pts[i].func_x;
                    }
                    //ctx.closePath();
                    ctx.lineWidth = 6;
                    ctx.strokeStyle = l == this.leg_index ? "red" : "blue";
                    ctx.stroke();

                    // draw corners and names
                    for (let i = 0; i < pts.length; i++) {
                        // save context's state (we will change it much)
                        ctx.save();

                        // WARNING: if more than 1 constraining point is there,
                        // we are forcing a curve to 4 points -> it will not be exact,
                        // therefore we draw 2 points: where it should be and where it is

                        // draw where the point on the function is
                        const mappt = this.applyTransformationMatrix({ x: pts[i].func_x, y: func(pts[i].func_x) }, leg.matrix_func2cropmap);
                        const [xf, yf] = this.mapedit.getImage2CanvasCoords(mappt.x, mappt.y);
                        ctx.beginPath();
                        ctx.fillStyle = 'none';
                        ctx.strokeStyle = (l == this.leg_index) ? ((i == this.mapedit.selectedPoint)) ? "green" : "red" : "blue";
                        ctx.lineWidth = 3;
                        ctx.setLineDash([5, 3]);
                        ctx.arc(xf, yf, 12, 0, 2 * Math.PI);
                        ctx.stroke()
                        ctx.font = "14px serif";
                        const txt = `${pts[i].func_x.toFixed(2)}, ${func(pts[i].func_x).toFixed(2)}`
                        ctx.setLineDash([]);
                        ctx.lineWidth = 1;
                        ctx.strokeText(txt, xf + 15, yf + i * 10);
                        ctx.fillStyle = "black";
                        ctx.fillText(txt, xf + 15, yf + i * 10);

                        // draw the where we wanted to force this point
                        const [x, y] = this.mapedit.getImage2CanvasCoords(pts[i].x, pts[i].y);
                        ctx.beginPath();
                        ctx.fillStyle = (l == this.leg_index) ? ((i == this.mapedit.selectedPoint)) ? "green" : "red" : "blue";
                        ctx.arc(x, y, 12, 0, 2 * Math.PI);
                        ctx.fill();

                        // restore the state
                        ctx.restore();
                    }

                    // draw extra point
                    if (this.extrapoint!=null) {
                        const [x, y] = this.mapedit.getImage2CanvasCoords(this.extrapoint[0], this.extrapoint[1]);
                        ctx.beginPath();
                        ctx.fillStyle = "purple";
                        ctx.arc(x, y, 12, 0, 2 * Math.PI);
                        ctx.fill();
                    }
                }
            }
        }
    }


    /**
     * Apply a 2D transformation matrix to a point.
     * @param {{x: number, y: number}} point - Original point.
     * @param {number[][]} matrix - 3x3 transformation matrix as nested arrays.
     * @returns {{x: number, y: number}} Transformed point.
     */
    private applyTransformationMatrix(point: {x: number, y: number}, matrix: number[][]) {
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
