import { ComponentFixture, TestBed } from '@angular/core/testing';

import { MathEditComponent } from './math-edit.component';

describe('MathEditComponent', () => {
  let component: MathEditComponent;
  let fixture: ComponentFixture<MathEditComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MathEditComponent]
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(MathEditComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
