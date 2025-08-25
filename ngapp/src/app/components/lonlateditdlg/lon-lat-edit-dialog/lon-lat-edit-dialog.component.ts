import { Component, Inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatOptionModule } from '@angular/material/core';
import { MatSelectModule } from '@angular/material/select';
import { FlexModule } from '@ngbracket/ngx-layout';

const PRECISION = -6;

@Component({
    selector: 'app-lon-lat-edit-dialog',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        ReactiveFormsModule,
        MatFormFieldModule,
        MatInputModule,
        MatOptionModule,
        MatSelectModule,
        MatDialogModule,
        MatButtonModule,
        MatButtonToggleModule,
        FlexModule,
    ],
    templateUrl: './lon-lat-edit-dialog.component.html',
    styleUrl: './lon-lat-edit-dialog.component.css'
})
export class LonLatEditDialogComponent {
    lonDecimal: number;
    latDecimal: number;
    lonDeg = 0; lonMin = 0; lonSec = 0; lonHem: 'E' | 'W' | 'N' | 'S' = 'E';
    latDeg = 0; latMin = 0; latSec = 0; latHem: 'E' | 'W' | 'N' | 'S' = 'N';
    mode: string = "decimal";

    constructor(
        private dialogRef: MatDialogRef<LonLatEditDialogComponent>,
        @Inject(MAT_DIALOG_DATA) public data: { lon: number, lat: number }
    ) {
        this.lonDecimal = this.roundTo(data.lon, PRECISION);
        this.latDecimal = this.roundTo(data.lat, PRECISION);
    }
    
    close(save: boolean) {
        if (this.mode === 'dms') {
            // ensure canonical decimal is up to date
            this.latDecimal = this.toDecimal(this.latDeg, this.latMin, this.latSec, this.latHem);
            this.lonDecimal = this.toDecimal(this.lonDeg, this.lonMin, this.lonSec, this.lonHem);
        }
        this.dialogRef.close({ lon: this.lonDecimal, lat: this.latDecimal, save: save });
    }

    onModeChange(newMode: 'decimal' | 'dms') {
        if (newMode === 'dms' && this.mode === 'decimal') {
            // decimal -> dms
            const lat = this.fromDecimal(this.latDecimal, true);
            this.latDeg = lat.deg; this.latMin = lat.min; this.latSec = lat.sec; this.latHem = lat.hem;

            const lon = this.fromDecimal(this.lonDecimal, false);
            this.lonDeg = lon.deg; this.lonMin = lon.min; this.lonSec = lon.sec; this.lonHem = lon.hem;
        }

        if (newMode === 'decimal' && this.mode === 'dms') {
            // dms -> decimal
            this.latDecimal = this.toDecimal(this.latDeg, this.latMin, this.latSec, this.latHem);
            this.lonDecimal = this.toDecimal(this.lonDeg, this.lonMin, this.lonSec, this.lonHem);
        }

        this.mode = newMode;
    }

    toDecimal(deg: number, min: number, sec: number, hem: 'N' | 'S' | 'E' | 'W'): number {
        let val = deg + min / 60 + sec / 3600;
        if (hem === 'S' || hem === 'W') val = -val;
        return this.roundTo(val, PRECISION);
    }

    fromDecimal(decimal: number, isLat: boolean) {
        const hem: 'N'|'S'|'E'|'W' = decimal < 0
            ? (isLat ? 'S' : 'W')
            : (isLat ? 'N' : 'E');
        const abs = Math.abs(decimal);
        const deg = Math.floor(abs);
        const minFloat = (abs - deg) * 60;
        const min = Math.floor(minFloat);
        const sec = Math.round((minFloat - min) * 60);
        return { deg, min, sec, hem };
    }

    roundTo(x: number, digits: number): number {
        return Math.round((x + Number.EPSILON) * 10 ** -digits) / 10 ** -digits;
    }
}
