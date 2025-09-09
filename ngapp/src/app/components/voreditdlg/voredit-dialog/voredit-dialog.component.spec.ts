import { ComponentFixture, TestBed } from '@angular/core/testing';

import { VOREditDialogComponent } from './voredit-dialog.component';

describe('VOREditDialogComponent', () => {
  let component: VOREditDialogComponent;
  let fixture: ComponentFixture<VOREditDialogComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [VOREditDialogComponent]
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(VOREditDialogComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
