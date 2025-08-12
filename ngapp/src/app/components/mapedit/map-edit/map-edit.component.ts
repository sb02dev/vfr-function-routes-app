import { AfterViewInit, Component, ElementRef, EventEmitter, Input, OnDestroy, Output, ViewChild } from '@angular/core';
import { MatIconModule } from "@angular/material/icon";
import { CommonModule } from '@angular/common';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { MatButtonModule } from '@angular/material/button';
import { Subscription } from 'rxjs';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { MatTooltipModule } from '@angular/material/tooltip';

import { ImageEditService } from '../../../services/image-edit.service';
import { ImageEditMessage } from '../../../models/image-edit-msg';
import { TileService } from '../../../services/tile.service';
import { environment } from '../../../../environments/environment';

@Component({
    selector: 'app-map-edit',
    standalone: true,
    imports: [
        CommonModule,
        MatIconModule,
        MatButtonModule,
        MatTooltipModule,
        FlexLayoutModule,
    ],
    templateUrl: './map-edit.component.html',
    styleUrl: './map-edit.component.css'
})
export class MapEditComponent implements AfterViewInit, OnDestroy {

    // the message subscriptions
    subs: Subscription;

    // inputs and events
    @Input() panelWidth: string = '50px';
    @Output() drawOverlay = new EventEmitter();
    @Output() enumPoints = new EventEmitter<(i: number, map_coords: boolean, x: number, y: number, w: number | undefined, h: number | undefined) => boolean>();
    @Output() addPointAt = new EventEmitter<{ x: number, y: number, callback: () => void }>();
    @Output() movePointTo = new EventEmitter<{ i: number, ex: number, ey: number, dx: number, dy: number, x: number, y: number, callback: () => void }>();
    @Output() finalizePoints = new EventEmitter();

    // canvases
    @ViewChild('bgCanvas', { static: true }) bgCanvasRef!: ElementRef<HTMLCanvasElement>;
    @ViewChild('overlayCanvas', { static: true }) overlayCanvasRef!: ElementRef<HTMLCanvasElement>;
    @ViewChild('svgContainer', { static: true }) svgContainer!: ElementRef<HTMLDivElement>;
    @ViewChild('pointerCapture', { static: true }) pointerCapture!: ElementRef<HTMLDivElement>;
    private bgResize!: ResizeObserver;
    public svgContent: SafeHtml = '';

    // tool selection
    public selectedTool: string = 'panzoom';

    // pointer tracking for pan/pinch
    private pointers = new Map<number, PointerEvent>();
    private initialPinchDistance = 0;
    private initialViewAtPinch: any = null;
    private initialPinchCenter: { x: number, y: number } | null = null;
    private clickTimer: any;
    private viewWindow = { x0: 0, y0: 0, x1: 4, y1: 4 }; // we store view window in image-space: x0,y0,x1,y1
    private panStart: { x: number, y: number } | null = null;
    private zoomFactor: number = 1.1; // how much to zoom in/out per scroll step

    // tile related
    private tilesetParams!: { tilesetName: string, dpi: number };
    private tileSize: { x: number, y: number } = { x: 0, y: 0 };
    private tileCount: { x: number, y: number } = { x: 0, y: 0 };
    private tileRange: { x: [number, number], y: [number, number] } = { x: [0, 0], y: [0, 0] };
    private tileCrop: { x0: number, y0: number, x1: number, y1: number } = { x0: 0, y0: 0, x1: 0, y1: 0 };
    private imageSize: { x: number, y: number } = { x: 0, y: 0 };
    get dpi() { return this.tilesetParams.dpi }

    // point edit variables
    private selectionDistance: number = 10.;
    selectedPoint: number | null = null;


    // ---------- component lifecycle ----------
    constructor(private imgsrv: ImageEditService, private tilesvc: TileService, private sanitizer: DomSanitizer) {
        this.subs = this.imgsrv.channel.subscribe((msg: ImageEditMessage) => {
            this.receiveServerMessage(msg);
        });
    }
    
    ngAfterViewInit(): void {
        // setup resize handlers
        this.bgResize = new ResizeObserver(() => {
            this.onScreenResized();
        });
        this.bgResize.observe(this.bgCanvasRef.nativeElement);

    }

    ngOnDestroy(): void {
        // stop observers
        this.bgResize.disconnect();
        this.subs.unsubscribe();
    }

    
    // ---------- public property hooks ----------
    public setSVG(svgstr: string) {
        this.svgContainer.nativeElement.style.width = `${this.imageSize.x}px`;
        this.svgContainer.nativeElement.style.height = `${this.imageSize.y}px`;
        this.svgContent = this.sanitizer.bypassSecurityTrustHtml(svgstr ?? '');
        setTimeout(() => { this.updateSVGTransform(); }, 500);
    }


    // ---------- communication with server ----------
    private receiveServerMessage(msg: ImageEditMessage) {
        if (msg.type === 'tiled-image') {
            // we have an image header, get ready to receive the image tiles
            // save the image data (tilesize & tilecount)
            this.tilesetParams = { tilesetName: msg['tilesetname'], dpi: msg['dpi'] };
            this.tileSize = msg['tilesize'];
            this.tileCount = msg['tilecount'];
            this.imageSize = msg['imagesize'];
            this.tileRange = msg['tilerange'];
            this.tileCrop = msg['tilecrop'];
            // setup the SVG container
            if (msg['additional_data'] && msg['additional_data']['svg_overlay']) {
                this.setSVG(msg['additional_data']['svg_overlay']);
            }
            // zoom to fit - delayed because for some reason this is not always done
            setTimeout(() => { this.zoomToAll(); }, 500);
            // redraw with no image
            this.drawBackgroundTransformed();
        }
    }

    // ---------- button events ----------
    resetView() {
        this.viewWindow = {
            x0: 0, x1: this.bgCanvasRef.nativeElement.width,
            y0: 0, y1: this.bgCanvasRef.nativeElement.height
        };
        this.drawBackgroundTransformed();
        this.updateSVGTransform();
        this.drawOverlayTransformed();
    }

    zoomToAll() {
        let imw = 0;
        let imh = 0;
        imw = this.imageSize.x;
        imh = this.imageSize.y;
        const canvasw = this.bgCanvasRef.nativeElement.width;
        const canvash = this.bgCanvasRef.nativeElement.height;
        const widthratio = imw / canvasw;
        const heightratio = imh / canvash;
        if (widthratio > heightratio) {
            this.viewWindow = { x0: 0, x1: imw, y0: 0, y1: canvash*widthratio};
        } else {
            this.viewWindow = { x0: 0, x1: canvasw * heightratio, y0: 0, y1: imh };
        }
        this.drawBackgroundTransformed();
        this.updateSVGTransform();
        this.drawOverlayTransformed();
    }


    // ---------- pointer events ----------
    onPointerDown(e: PointerEvent) {
        (e.target as Element).setPointerCapture(e.pointerId);
        this.pointers.set(e.pointerId, e);

        if (this.pointers.size === 1) {
            // start pan or edit
            if (this.selectedTool == 'panzoom') {
                this.panStart = { x: e.offsetX, y: e.offsetY };
            } else if (this.selectedTool == 'edit') {
                if (this.clickTimer) {
                    clearTimeout(this.clickTimer);
                    this.clickTimer = null;
                    // Handle double-click
                    e.preventDefault();
                    this.doublePointerDown(e);
                } else {
                    this.clickTimer = setTimeout(() => {
                        this.clickTimer = null;
                        // Handle single click
                        this.singlePointerDown(e);
                    }, environment.DOUBLE_CLICK_DELAY); // Adjust the delay to match your double-click threshold
                }
            }
        } else if (this.pointers.size === 2) {
            // start pinch
            const points = Array.from(this.pointers.values());
            this.initialPinchDistance = this.distance(points[0], points[1]);
            this.initialViewAtPinch = { ...this.viewWindow };
            this.initialPinchCenter = {
                x: (points[0].offsetX + points[1].offsetX) / 2,
                y: (points[0].offsetY + points[1].offsetY) / 2
            };
        }
    }

    private singlePointerDown(e: PointerEvent) {
        if (e.button === 1 || e.button === 0) { // middle or left
            this.panStart = { x: e.offsetX, y: e.offsetY };
        }
        const x = e.offsetX;
        const y = e.offsetY;
        if (e.button == 0) { // left click moves a point
            this.enumPoints.emit((i: number,
                map_coords: boolean,
                xx: number, yy: number,
                ww: number | undefined = undefined, hh: number | undefined = undefined) => {
                let [xp, yp] = [xx, yy];
                let [wp, hp] = [ww, hh];
                // if parameters are in map coordinates we convert them
                if (map_coords) {
                    [xp, yp] = this.getImage2CanvasCoords(xx, yy);
                    if (ww && hh) {
                        const [xp1, yp1] = this.getImage2CanvasCoords(xx + ww, yy + hh);
                        [wp, hp] = [xp1 - xp, yp1 - yp];
                    }
                }
                if (!ww && !hh) {
                    // we got a point
                    const dist = Math.sqrt((xp - x) ** 2 + (yp - y) ** 2);
                    if (dist < this.selectionDistance) {
                        this.selectedPoint = i;
                        this.drawOverlayTransformed();
                        return false;
                    } else {
                        return true;
                    }
                } else {
                    // we got a rectangle
                    if ((xp <= x) && (x <= xp + wp!) && (yp <= y) && (y <= yp + hp!)) {
                        this.selectedPoint = i;
                        this.drawOverlayTransformed();
                        return false;
                    } else {
                        return true;
                    }
                }
            });
        }
    }

    private doublePointerDown(e: PointerEvent) {
        const x = e.offsetX;
        const y = e.offsetY;
        if (e.button == 0) { // left double-click creates a new point
            const [wx, wy] = this.getCanvas2ImageCoords(x, y);
            this.addPointAt.emit({
                x: wx, y: wy, callback: () => {
                    this.drawOverlayTransformed();
                }
            });
        }
    }

    onPointerMove(e: PointerEvent) {
        if (!this.pointers.has(e.pointerId)) return;
        this.pointers.set(e.pointerId, e);

        if (this.pointers.size === 1 && this.panStart) {
            const cur = { x: e.offsetX, y: e.offsetY };
            const dx = cur.x - this.panStart.x;
            const dy = cur.y - this.panStart.y;
            this.panStart = cur;

            if (this.selectedTool === 'panzoom') {
                this.panByPixels(dx, dy);
            } else if (this.selectedTool === 'edit') {
                if (this.selectedPoint !== null && this.panStart) {
                    const [x, y] = this.getCanvas2ImageCoords(cur.x, cur.y);
                    this.movePointTo.emit({
                        i: this.selectedPoint,
                        ex: e.offsetX,
                        ey: e.offsetY,
                        dx: dx,
                        dy: dy,
                        x: x,
                        y: y,
                        callback: () => this.drawOverlayTransformed(),
                    })
                }
            }
        } else if (this.pointers.size === 2) {
            const points = Array.from(this.pointers.values());
            // zoom
            const curDistance = this.distance(points[0], points[1]);
            const scaleRatio = curDistance / this.initialPinchDistance;
            // pan
            const newCenter = {
                x: (points[0].offsetX + points[1].offsetX) / 2,
                y: (points[0].offsetY + points[1].offsetY) / 2
            }
            const dx =  newCenter.x - this.initialPinchCenter!.x
            const dy = newCenter.y - this.initialPinchCenter!.y
            this.initialPinchCenter = newCenter; // must change, otherwise there would be drift
            // do it
            this.panByPixels(dx, dy);
            this.pinchZoom(scaleRatio);
        }
    }

    onPointerUp(e: PointerEvent) {
        try { (e.target as Element).releasePointerCapture(e.pointerId); } catch { }
        this.pointers.delete(e.pointerId);
        if (this.pointers.size === 0) {
            if (this.selectedTool == 'panzoom') {
                this.panStart = null;
            } else if (this.selectedTool == 'edit') {
                this.panStart = null;
                this.selectedPoint = null;
                this.drawOverlayTransformed();
                this.finalizePoints.emit();
            }
        } else if (this.pointers.size === 1) {
            // promote remaining pointer to pan
            const remaining = Array.from(this.pointers.values())[0];
            this.panStart = { x: remaining.offsetX, y: remaining.offsetY };
        }
    }

    onPointerCancel(e: PointerEvent) {
        this.pointers.delete(e.pointerId);
        this.panStart = null;
        this.initialPinchDistance = 0;
        this.initialViewAtPinch = null;
    }

    onMouseWheel(e: WheelEvent) {
        e.preventDefault();
        const mouseX = e.offsetX;
        const mouseY = e.offsetY;
        const zoomIn = e.deltaY < 0;

        const x = mouseX;
        const y = mouseY;

        [this.viewWindow.x0, this.viewWindow.x1] = this.zoomWindow(this.viewWindow.x0, this.viewWindow.x1, x, zoomIn);
        [this.viewWindow.y0, this.viewWindow.y1] = this.zoomWindow(this.viewWindow.y0, this.viewWindow.y1, y, zoomIn);

        this.drawBackgroundTransformed();
        this.updateSVGTransform();
        this.drawOverlayTransformed();
    }


    // ---------- canvas draw ----------
    private drawGeneration = 0;
    private async drawBackgroundTransformed() {
        // get references and clear canvas
        const canvas = this.bgCanvasRef.nativeElement;
        const ctx = canvas.getContext('2d')!;

        const myGen = ++this.drawGeneration; // unique ID for this draw session

        // Create offscreen buffer
        const offscreen = new OffscreenCanvas(canvas.width, canvas.height);
        const offctx = offscreen.getContext('2d')!;
        // clear it
        offctx.clearRect(0, 0, canvas.width, canvas.height);

        // get tile order (center first)
        const orderedTiles = this.getTileOrder();

        // draw tiles incrementally in priority order
        for (const { xi, yi } of orderedTiles) {
            // quit early if a new generation has started
            if (myGen !== this.drawGeneration) return;
            // otherwise start drawing
            await this.drawTileTransformed(xi, yi, offscreen, offctx, myGen);
            // flip to visible
            ctx.drawImage(offscreen, 0, 0);
        }

        // flip to visible
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(offscreen, 0, 0);
    }

    private async drawTileTransformed(xi: number, yi: number,
                                      canvas: HTMLCanvasElement | OffscreenCanvas, 
                                      ctx: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D,
                                      myGen: number) {
        if (myGen !== this.drawGeneration) return; // cancel if outdated
        
        // calculate coordinates
        let [x0, y0] = [
            (xi - this.tileRange.x[0]) * this.tileSize.x - this.tileCrop.x0,
            (yi - this.tileRange.y[0]) * this.tileSize.y - this.tileCrop.y0
        ];
        let [x1, y1] = [
            (xi - this.tileRange.x[0] + 1) * this.tileSize.x - this.tileCrop.x0,
            (yi - this.tileRange.y[0] + 1) * this.tileSize.y - this.tileCrop.y0
        ];
        let [imx0, imy0] = this.getImage2CanvasCoords(x0, y0);
        let [imx1, imy1] = this.getImage2CanvasCoords(x1, y1);
        // draw only if it is in viewport
        if ((imx0 <= canvas.width && imx1 >= 0) && (imy0 <= canvas.height && imy1 >= 0)) {
            const bitmap = await this.tilesvc.getTile(this.tilesetParams.tilesetName, this.tilesetParams.dpi, xi, yi);
            if (myGen !== this.drawGeneration) return; // cancel if outdated
            if (bitmap) {
                let [sx, sy, sw, sh] = [0, 0, bitmap.width, bitmap.height]; // initiate with no crop

                if ((bitmap.width != this.tileSize.x) || (bitmap.height != this.tileSize.y)) {
                    // tile is smaller than the default size (last in the row/column)
                    [x1, y1] = [x0 + sw - 1, y0 + sh - 1];
                }

                // we have to crop the left side of the tile
                if (xi == this.tileRange.x[0] && this.tileCrop.x0 != 0) {
                    x0 += this.tileCrop.x0; // tile will shift right
                    sx += this.tileCrop.x0; // we will start from this x coord in the tile image
                    sw -= this.tileCrop.x0; // we will use this many pixels horizontally from the tile image
                }

                // we have to crop the top side of the tile
                if (yi == this.tileRange.y[0] && this.tileCrop.y0 != 0) {
                    y0 += this.tileCrop.y0; // tile will shift down
                    sy += this.tileCrop.y0; // we will start from this y coord in the tile image
                    sh -= this.tileCrop.y0; // we will use this many pixels vertically from the tile image
                }

                // we have to crop the right side of the tile
                if (xi == this.tileRange.x[1]-1 && this.tileCrop.x1 != 0) {
                    x1 -= this.tileCrop.x1; // tile's right side will shift left
                    sw -= this.tileCrop.x1; // we will use this many pixels horizontally from the tile image
                }

                // we have to crop the bottom side of the tile
                if (yi == this.tileRange.y[1]-1 && this.tileCrop.y1 != 0) {
                    y1 -= this.tileCrop.y1; // tile's right side will shift left
                    sh -= this.tileCrop.y1; // we will use this many pixels horizontally from the tile image
                }

                // recalculate the pan/zoom on the destination coordinates
                [imx0, imy0] = this.getImage2CanvasCoords(x0, y0);
                [imx1, imy1] = this.getImage2CanvasCoords(x1, y1);

                ctx.drawImage(
                    bitmap,
                    sx, sy, sw, sh,
                    imx0, imy0, imx1 - imx0, imy1 - imy0
                );

            }
        }
    }

    private getTileOrder(): { xi: number, yi: number, dist: number }[] {
        const cx = (this.tileRange.x[1] + this.tileRange.x[0]) / 2;
        const cy = (this.tileRange.y[1] + this.tileRange.y[0]) / 2;

        const tiles: { xi: number, yi: number, dist: number }[] = [];
        for (let xi = this.tileRange.x[0]; xi < this.tileRange.x[1]; xi++) {
            for (let yi = this.tileRange.y[0]; yi < this.tileRange.y[1]; yi++) {
                const dx = xi + 0.5 - cx;
                const dy = yi + 0.5 - cy;
                const dist = Math.sqrt(dx * dx + dy * dy);
                tiles.push({ xi, yi, dist });
            }
        }

        // sort by distance from center (smallest first)
        tiles.sort((a, b) => a.dist - b.dist);
        return tiles;
    }

    drawOverlayTransformed() {
        this.drawOverlay.emit({
            canvas: this.overlayCanvasRef.nativeElement,
            imgWidth: this.imageSize.x,
            imgHeight: this.imageSize.y,
        });
    }
    
    updateSVGTransform() {
        const canvas: HTMLCanvasElement = this.bgCanvasRef.nativeElement;
        const [xmin, xmax] = [this.viewWindow.x0, this.viewWindow.x1];
        const [ymin, ymax] = [this.viewWindow.y0, this.viewWindow.y1];
        const xscale = canvas.width / (xmax - xmin);
        const yscale = canvas.height / (ymax - ymin);
        const scale = Math.min(xscale, yscale);
        this.svgContainer.nativeElement.children.item(0)?.setAttribute('width', '100%');
        this.svgContainer.nativeElement.children.item(0)?.setAttribute('height', '100%');
        this.svgContainer.nativeElement.style.transform = `translate(${-this.viewWindow.x0 * scale}px, ${-this.viewWindow.y0 * scale}px) scale(${scale})`
    }


    // ---------- pan and zoom math ----------
    getImage2CanvasCoords(x: number, y: number) {
        const canvas: HTMLCanvasElement = this.bgCanvasRef.nativeElement;
        const [xmin, xmax] = [this.viewWindow.x0, this.viewWindow.x1];
        const [ymin, ymax] = [this.viewWindow.y0, this.viewWindow.y1];
        const xscale = canvas.width / (xmax - xmin);
        const yscale = canvas.height / (ymax - ymin);

        return [(x - xmin) * xscale, (y - ymin) * yscale];
    }

    getCanvas2ImageCoords(x: number, y: number) {
        const canvas: HTMLCanvasElement = this.bgCanvasRef.nativeElement;
        const [xmin, xmax] = [this.viewWindow.x0, this.viewWindow.x1];
        const [ymin, ymax] = [this.viewWindow.y0, this.viewWindow.y1];
        const xscale = canvas.width / (xmax - xmin);
        const yscale = canvas.height / (ymax - ymin);

        return [x / xscale + xmin, y / yscale + ymin];
    }

    getScale(): { x: number, y: number } {
        const canvas: HTMLCanvasElement = this.bgCanvasRef.nativeElement;
        const [xmin, xmax] = [this.viewWindow.x0, this.viewWindow.x1];
        const [ymin, ymax] = [this.viewWindow.y0, this.viewWindow.y1];
        const xscale = canvas.width / (xmax - xmin);
        const yscale = canvas.height / (ymax - ymin);
        return { x: xscale, y: yscale };
    }

    private panByPixels(dx: number, dy: number) {
        const canvas: HTMLCanvasElement = this.bgCanvasRef.nativeElement;
        const [xmin, xmax] = [this.viewWindow.x0, this.viewWindow.x1];
        const [ymin, ymax] = [this.viewWindow.y0, this.viewWindow.y1];
        const xscale = canvas.width / (xmax - xmin);
        const yscale = canvas.height / (ymax - ymin);
        const scale = Math.min(xscale, yscale);

        const deltaX = dx / scale;
        const deltaY = dy / scale;

        this.viewWindow = {
            x0: xmin - deltaX, x1: xmax - deltaX,
            y0: ymin - deltaY, y1: ymax - deltaY
        };

        this.drawBackgroundTransformed();
        this.updateSVGTransform();
        this.drawOverlayTransformed();
    }

    private pinchZoom(scaleRatio: number) {
        if (!this.initialViewAtPinch) return;
        const centerX = (this.viewWindow.x0 + this.viewWindow.x1) / 2;
        const centerY = (this.viewWindow.y0 + this.viewWindow.y1) / 2;
        const newWidth = (this.initialViewAtPinch.x1 - this.initialViewAtPinch.x0) / scaleRatio;
        const newHeight = (this.initialViewAtPinch.y1 - this.initialViewAtPinch.y0) / scaleRatio;
        this.viewWindow.x0 = centerX - newWidth / 2;
        this.viewWindow.x1 = centerX + newWidth / 2;
        this.viewWindow.y0 = centerY - newHeight / 2;
        this.viewWindow.y1 = centerY + newHeight / 2;
        this.drawBackgroundTransformed();
        this.updateSVGTransform();
        this.drawOverlayTransformed();
    }

    private zoomWindow(
        xMin: number,
        xMax: number,
        mouseX: number,
        zoomIn: boolean,
        zoomFactor: number = 1.1,
        minSpan: number = 1e-3
    ): [number, number] {
        const span = xMax - xMin;
        const centerRatio = (mouseX - xMin) / span;

        const scale = zoomIn ? 1 / zoomFactor : zoomFactor;
        let newSpan = span * scale;

        // Prevent over-zoom
        if (newSpan < minSpan) newSpan = minSpan;

        const newMin = mouseX - centerRatio * newSpan;
        const newMax = mouseX + (1 - centerRatio) * newSpan;

        return [newMin, newMax];
    }

    private onScreenResized() {
        const w = this.bgCanvasRef.nativeElement.clientWidth;
        const h = this.bgCanvasRef.nativeElement.clientHeight;
        // update view window
        const scale = this.getScale();
        console.log(scale);
        this.viewWindow.x1 = this.viewWindow.x0 + w / scale.x;
        this.viewWindow.y1 = this.viewWindow.y0 + h / scale.y;
        // update canvas size
        this.bgCanvasRef.nativeElement.width = w;
        this.bgCanvasRef.nativeElement.height = h;
        this.overlayCanvasRef.nativeElement.width = w;
        this.overlayCanvasRef.nativeElement.height = h;
        // redraw
        this.drawBackgroundTransformed();
        this.updateSVGTransform();
        this.drawOverlayTransformed();
    }


    // ---------- helpers ----------
    private distance(a: PointerEvent, b: PointerEvent) {
        const dx = a.offsetX - b.offsetX;
        const dy = a.offsetY - b.offsetY;
        return Math.hypot(dx, dy);
    }

}
