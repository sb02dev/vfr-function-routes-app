import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MAT_DIALOG_DATA, MatDialogRef, MatDialogModule } from '@angular/material/dialog';

@Component({
    selector: 'app-dmearc-func-xcalc-dialog',
    standalone: true,
    imports: [
        MatDialogModule,
        CommonModule,
        FormsModule,
        ReactiveFormsModule,
        MatFormFieldModule,
        MatInputModule,
        MatButtonModule,
        MatButtonToggleModule,
    ],
    templateUrl: './dmearc-func-xcalc-dialog.component.html',
    styleUrl: './dmearc-func-xcalc-dialog.component.css'
})
export class DMEArcFuncXCalcDialogComponent {
    radial1: number = 0;
    radial2: number = 0;
    math = Math;

    constructor(
        private dialogRef: MatDialogRef<DMEArcFuncXCalcDialogComponent>,
        @Inject(MAT_DIALOG_DATA) public data: { radial1: number, radial2: number }
    ) {
        this.radial1 = data.radial1;
        this.radial2 = data.radial2;
    }
    
    close(save: boolean) {
        const x = Math.cos((Math.abs(this.radial1 - this.radial2) / 2 + 90) * Math.PI / 180);
        this.dialogRef.close({
            radial1: this.radial1,
            radial2: this.radial2,
            xmin: -x,
            xmax: x,
            save: save
        });
    }

}
