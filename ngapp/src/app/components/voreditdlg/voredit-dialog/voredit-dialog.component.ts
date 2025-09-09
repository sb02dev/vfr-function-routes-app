import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, ElementRef, Inject, Input, ViewChild } from '@angular/core';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MAT_DIALOG_DATA, MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatAutocompleteModule } from '@angular/material/autocomplete';

import { ImageEditService } from '../../../services/image-edit.service';
import { debounceTime, distinctUntilChanged, fromEvent, map, Observable, switchMap } from 'rxjs';

@Component({
    selector: 'app-voredit-dialog',
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
        MatAutocompleteModule,
    ],
    templateUrl: './voredit-dialog.component.html',
    styleUrl: './voredit-dialog.component.css'
})
export class VOREditDialogComponent implements AfterViewInit {
    vor: string = '';
    radial: number = 0;
    dme: number = 0;
    magn: number = 0;
    airport: string = '';
    mode: string = 'arc_point';

    @ViewChild('vorinp') vorinp!: ElementRef<HTMLInputElement>;
    filteredNavaids$!: Observable<string[]>;
    @ViewChild('airportinp') airportinp!: ElementRef<HTMLInputElement>;
    filteredAirports$!: Observable<string[]>;


    constructor(
        private imgsrv: ImageEditService,
        private dialogRef: MatDialogRef<VOREditDialogComponent>,
        @Inject(MAT_DIALOG_DATA) public data: {
            vor: string;
            radial: number,
            dme: number,
            magn: number,
            airport: string;
            mode: 'station' | 'arc_point' | 'airport'
        }
    ) {
        this.mode = data.mode ? data.mode : 'station';
        if (this.mode == 'airport') {
            this.airport = data.airport;   
        } else {
            this.vor = data.vor;
            this.radial = data.radial;
            this.dme = data.dme
            this.magn = data.magn;
        }
    }

    ngAfterViewInit() {
        if (this.mode !== 'airport') {
            this.filteredNavaids$ = fromEvent<InputEvent>(this.vorinp.nativeElement, 'input').pipe(
                map(event => (event.target as HTMLInputElement).value),
                debounceTime(300),                // wait for user to stop typing
                distinctUntilChanged(),
                switchMap(value => this.onQueryVORStations(value)) // call server
            );
        } else {
            this.filteredAirports$ = fromEvent<InputEvent>(this.airportinp.nativeElement, 'input').pipe(
                map(event => (event.target as HTMLInputElement).value),
                debounceTime(300),                // wait for user to stop typing
                distinctUntilChanged(),
                switchMap(value => this.onQueryAirports(value)) // call server
            );
        }
    }
    
    close(save: boolean) {
        this.dialogRef.close({
            vor: this.vor,
            radial: this.radial,
            dme: this.dme,
            magn: this.magn,
            airport: this.airport,
            mode: this.mode,
            save: save
        });
    }

    onModeChange(newMode: 'station' | 'arc_point') {
        this.mode = newMode;
    }

    onQueryVORStations(query: string): Observable<string[]> {
        return new Observable(observer => {
            this.imgsrv.send('get-vor-stations', (stations: string[]) => {
                observer.next(stations);
                observer.complete(); // complete after delivering results
            }, query);
        });
    }

    onQueryAirports(query: string): Observable<string[]> {
        return new Observable(observer => {
            this.imgsrv.send('get-airports', (airports: string[]) => {
                observer.next(airports);
                observer.complete(); // complete after delivering results
            }, query);
        });
    }

}
