import { ComponentFixture, TestBed } from '@angular/core/testing';

import { LonLatEditDialogComponent } from './lon-lat-edit-dialog.component';

describe('LonLatEditDialogComponent', () => {
  let component: LonLatEditDialogComponent;
  let fixture: ComponentFixture<LonLatEditDialogComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LonLatEditDialogComponent]
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(LonLatEditDialogComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
