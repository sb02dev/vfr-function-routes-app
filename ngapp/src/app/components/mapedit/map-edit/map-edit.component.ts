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

    // canvas and tool selection
    @ViewChild('bgCanvas', { static: true }) bgCanvasRef!: ElementRef<HTMLCanvasElement>;
    @ViewChild('overlayCanvas', { static: true }) overlayCanvasRef!: ElementRef<HTMLCanvasElement>;
    @ViewChild('svgContainer', { static: true }) svgContainer!: ElementRef<HTMLDivElement>;
    private bgResize!: ResizeObserver;
    baseImage: HTMLImageElement | null = null;
    public selectedTool: string = 'panzoom';
    public svgContent: SafeHtml = '';

    // tile related
    private tilesetParams!: { tilesetName: string, dpi: number };
    private tileSize: { x: number, y: number } = { x: 0, y: 0 };
    private tileCount: { x: number, y: number } = { x: 0, y: 0 };
    private tileRange: { x: [number, number], y: [number, number] } = { x: [0, 0], y: [0, 0] };
    private tileCrop: { x0: number, y0: number, x1: number, y1: number } = { x0: 0, y0: 0, x1: 0, y1: 0 };
    private imageSize: { x: number, y: number } = { x: 0, y: 0 };
    clickTimer: any;
    get dpi() { return this.tilesetParams.dpi }

    // pan and zoom variables
    private xlim: [number, number] = [0, 4];
    private ylim: [number, number] = [0, 4];
    private panStart: { x: number, y: number } | null = null;
    private zoomFactor: number = 1.1; // how much to zoom in/out per scroll step

    // point edit variables
    private selectionDistance: number = 10.;
    selectedPoint: number | null = null;


    constructor(private imgsrv: ImageEditService, private tilesvc: TileService, private sanitizer: DomSanitizer) {
        this.subs = this.imgsrv.channel.subscribe((msg: ImageEditMessage) => {
            if (msg.type === 'tiled-image') {
                // we have an image header, get ready to receive the image tiles
                // save the image data (tilesize & tilecount)
                this.tilesetParams = { tilesetName: msg['tilesetname'], dpi: msg['dpi'] };
                this.tileSize = msg['tilesize'];
                this.tileCount = msg['tilecount'];
                this.imageSize = msg['imagesize'];
                this.tileRange = msg['tilerange']
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
        });
    }
    

    public setSVG(svgstr: string) {
        this.svgContainer.nativeElement.style.width = `${this.imageSize.x}px`;
        this.svgContainer.nativeElement.style.height = `${this.imageSize.y}px`;
        this.svgContent = this.sanitizer.bypassSecurityTrustHtml(svgstr ?? '');
        setTimeout(() => { this.updateSVGTransform(); }, 500);
    }

    ngAfterViewInit(): void {
        // setup resize handlers
        this.bgResize = new ResizeObserver(() => {
            const w = this.bgCanvasRef.nativeElement.clientWidth;
            const h = this.bgCanvasRef.nativeElement.clientHeight;
            // update canvas size or layout
            this.bgCanvasRef.nativeElement.width = w;
            this.bgCanvasRef.nativeElement.height = h;
            this.xlim = [this.xlim[0], this.xlim[0] + w];
            this.ylim = [this.ylim[0], this.ylim[0] + h];
            this.overlayCanvasRef.nativeElement.width = w;
            this.overlayCanvasRef.nativeElement.height = h;
            // redraw
            this.drawBackgroundTransformed();
            this.updateSVGTransform();
            this.drawOverlayTransformed();
        });
        this.bgResize.observe(this.bgCanvasRef.nativeElement);

        // setup click handlers
        this.bgCanvasRef.nativeElement.addEventListener('mousedown', e => this.mouseDown(e));
        this.overlayCanvasRef.nativeElement.addEventListener('mousedown', e => this.mouseDown(e));

        this.bgCanvasRef.nativeElement.addEventListener('mousemove', e => this.mouseMove(e));
        this.overlayCanvasRef.nativeElement.addEventListener('mousemove', e => this.mouseMove(e));

        this.bgCanvasRef.nativeElement.addEventListener('mouseup', e => this.mouseUp(e));
        this.overlayCanvasRef.nativeElement.addEventListener('mouseup', e => this.mouseUp(e));

        this.bgCanvasRef.nativeElement.addEventListener('mouseleave', e => this.mouseLeave(e));
        this.overlayCanvasRef.nativeElement.addEventListener('mouseleave', e => this.mouseLeave(e));

        this.bgCanvasRef.nativeElement.addEventListener('wheel', e => this.mouseWheel(e), { passive: false });
        this.overlayCanvasRef.nativeElement.addEventListener('wheel', e => this.mouseWheel(e), { passive: false });

    }

    ngOnDestroy(): void {
        // stop observers
        this.bgResize.disconnect();
        this.subs.unsubscribe();
    }

    resetView() {
        this.xlim = [0, this.bgCanvasRef.nativeElement.width];
        this.ylim = [0, this.bgCanvasRef.nativeElement.height];
        this.drawBackgroundTransformed();
        this.updateSVGTransform();
        this.drawOverlayTransformed();
    }

    zoomToAll() {
        let imw = 0;
        let imh = 0;
        if (this.baseImage) {
            imw = this.baseImage.width;
            imh = this.baseImage.height;
        } else {
            imw = this.imageSize.x;
            imh = this.imageSize.y;
        }
        const canvasw = this.bgCanvasRef.nativeElement.width;
        const canvash = this.bgCanvasRef.nativeElement.height;
        const widthratio = imw / canvasw;
        const heightratio = imh / canvash;
        if (widthratio > heightratio) {
            this.xlim = [0,imw];
            this.ylim = [0,canvash*widthratio];
        } else {
            this.xlim = [0,canvasw*heightratio];
            this.ylim = [0,imh];
        }
        this.drawBackgroundTransformed();
        this.updateSVGTransform();
        this.drawOverlayTransformed();
    }

    private mouseDown(e: MouseEvent) {
        if (this.selectedTool == 'panzoom') {
            if (e.button === 1 || e.button === 0) {  // middle or left
                this.panStart = { x: e.offsetX, y: e.offsetY };
            }
        } else if (this.selectedTool == 'edit') {
            if (this.clickTimer) {
                clearTimeout(this.clickTimer);
                this.clickTimer = null;
                // Handle double-click
                this.doubleMouseDown(e);
            } else {
                this.clickTimer = setTimeout(() => {
                    this.clickTimer = null;
                    // Handle single click
                    this.singleMouseDown(e);
                }, environment.DOUBLE_CLICK_DELAY); // Adjust the delay to match your double-click threshold
            }
        }
    }

    private singleMouseDown(e: MouseEvent) {
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

    doubleMouseDown(e: MouseEvent) {
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

    private mouseMove(e: MouseEvent) {
        if (this.selectedTool == 'panzoom') {
            if (this.panStart) {
                const dx = e.offsetX - this.panStart.x;
                const dy = e.offsetY - this.panStart.y;
                this.panStart = { x: e.offsetX, y: e.offsetY };

                const canvas: HTMLCanvasElement = this.bgCanvasRef.nativeElement;
                const [xmin, xmax] = this.xlim;
                const [ymin, ymax] = this.ylim;
                const xscale = canvas.width / (xmax - xmin);
                const yscale = canvas.height / (ymax - ymin);
                const scale = Math.min(xscale, yscale);

                const deltaX = dx / scale;
                const deltaY = dy / scale;

                this.xlim = [xmin - deltaX, xmax - deltaX];
                this.ylim = [ymin - deltaY, ymax - deltaY];

                this.drawBackgroundTransformed();
                this.updateSVGTransform();
                this.drawOverlayTransformed();
            }
        } else if (this.selectedTool == 'edit') {
            if (this.selectedPoint !== null && this.panStart) {
                const dx = e.offsetX - this.panStart.x;
                const dy = e.offsetY - this.panStart.y;
                this.panStart = { x: e.offsetX, y: e.offsetY };
                const [x, y] = this.getCanvas2ImageCoords(e.offsetX, e.offsetY);
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
    }

    private mouseUp(e: MouseEvent) {
        if (this.selectedTool == 'panzoom') {
            this.panStart = null;
        } else if (this.selectedTool == 'edit') {
            this.panStart = null;
            this.selectedPoint = null;
            this.drawOverlayTransformed();
            this.finalizePoints.emit();
        }
    }

    private mouseLeave(e: MouseEvent) {
        this.panStart = null;
    }

    private mouseWheel(e: WheelEvent) {
        if (this.selectedTool == 'panzoom') {
            e.preventDefault();
            const canvas = this.overlayCanvasRef.nativeElement;
            const mouseX = e.offsetX;
            const mouseY = e.offsetY;
            const zoomIn = e.deltaY < 0;

            const x = mouseX;
            const y = mouseY;

            const [xmin, xmax] = this.xlim;
            const [ymin, ymax] = this.ylim;
            const scaleFact = zoomIn ? 1 / this.zoomFactor : this.zoomFactor;
            const scale = scaleFact * e.deltaY / 100.;

            this.xlim = this.zoomWindow(this.xlim, x, zoomIn);
            this.ylim = this.zoomWindow(this.ylim, y, zoomIn);

            this.drawBackgroundTransformed();
            this.updateSVGTransform();
            this.drawOverlayTransformed();
        }
    }

    private zoomWindow(
        xlim: [number, number],
        mouseX: number,
        zoomIn: boolean,
        zoomFactor: number = 1.1,
        minSpan: number = 1e-3
    ): [number, number] {
        const [xMin, xMax] = xlim;
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

    drawBackgroundImage(base64: string): void {
        const img = new Image();
        img.onload = () => {
            this.baseImage = img;
            this.zoomToAll();
        };
        img.src = 'data:image/png;base64,' + base64;
    }

    private drawGeneration = 0;

    private async drawBackgroundTransformed() {
        // get references and clear canvas
        const canvas = this.bgCanvasRef.nativeElement;
        const ctx = canvas.getContext('2d')!;

        if (this.baseImage) { // legacy method: one large chunk
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            this.drawFullImage(canvas, ctx);
        } else { // new method: show tiles
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
    }

    private drawFullImage(canvas: HTMLCanvasElement, ctx: CanvasRenderingContext2D) {
        if (!this.baseImage) return;

        // get the image data
        const img = this.baseImage;
        const imgWidth = img.width;
        const imgHeight = img.height;

        // Mapping from data coords to image pixels
        const [xmin, xmax] = this.xlim;
        const [ymin, ymax] = this.ylim;

        // Determine crop region in image space (sx, sy, sw, sh)
        const sx = xmin;
        const sy = ymin;
        const sw = xmax - xmin;
        const sh = ymax - ymin;

        // Destination: full canvas
        ctx.drawImage(img, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
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

                // console.log(`(${xi},${yi}) => (${imx0},${imy0})-(${imx1},${imy1}) x (${bitmap.width}, ${bitmap.height})`);

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
            imgWidth: this.baseImage?.width,
            imgHeight: this.baseImage?.height,
        });
    }
    
    updateSVGTransform() {
        const canvas: HTMLCanvasElement = this.bgCanvasRef.nativeElement;
        const [xmin, xmax] = this.xlim;
        const [ymin, ymax] = this.ylim;
        const xscale = canvas.width / (xmax - xmin);
        const yscale = canvas.height / (ymax - ymin);
        const scale = Math.min(xscale, yscale);
        this.svgContainer.nativeElement.children.item(0)?.setAttribute('width', '100%');
        this.svgContainer.nativeElement.children.item(0)?.setAttribute('height', '100%');
        this.svgContainer.nativeElement.style.transform = `translate(${-this.xlim[0] * scale}px, ${-this.ylim[0] * scale}px) scale(${scale})`
    }

    getImage2CanvasCoords(x: number, y: number) {
        const canvas: HTMLCanvasElement = this.bgCanvasRef.nativeElement;
        const [xmin, xmax] = this.xlim;
        const [ymin, ymax] = this.ylim;
        const xscale = canvas.width / (xmax - xmin);
        const yscale = canvas.height / (ymax - ymin);

        return [(x - xmin) * xscale, (y - ymin) * yscale];
    }

    getCanvas2ImageCoords(x: number, y: number) {
        const canvas: HTMLCanvasElement = this.bgCanvasRef.nativeElement;
        const [xmin, xmax] = this.xlim;
        const [ymin, ymax] = this.ylim;
        const xscale = canvas.width / (xmax - xmin);
        const yscale = canvas.height / (ymax - ymin);

        return [x / xscale + xmin, y / yscale + ymin];
    }

    getScale(): { x: number, y: number } {
        const canvas: HTMLCanvasElement = this.bgCanvasRef.nativeElement;
        const [xmin, xmax] = this.xlim;
        const [ymin, ymax] = this.ylim;
        const xscale = canvas.width / (xmax - xmin);
        const yscale = canvas.height / (ymax - ymin);
        return { x: xscale, y: yscale };
    }

}
