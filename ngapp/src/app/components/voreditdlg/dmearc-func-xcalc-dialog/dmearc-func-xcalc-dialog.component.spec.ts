import { ComponentFixture, TestBed } from '@angular/core/testing';

import { DMEArcFuncXCalcDialogComponent } from './dmearc-func-xcalc-dialog.component';

describe('DMEArcFuncXCalcDialogComponent', () => {
  let component: DMEArcFuncXCalcDialogComponent;
  let fixture: ComponentFixture<DMEArcFuncXCalcDialogComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DMEArcFuncXCalcDialogComponent]
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(DMEArcFuncXCalcDialogComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
