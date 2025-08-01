import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Step4AnnotationsEditComponent } from './step4-annotations-edit.component';

describe('Step4AnnotationsEditComponent', () => {
  let component: Step4AnnotationsEditComponent;
  let fixture: ComponentFixture<Step4AnnotationsEditComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Step4AnnotationsEditComponent]
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(Step4AnnotationsEditComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
