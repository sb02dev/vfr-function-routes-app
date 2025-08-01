import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Step5AddTracksComponent } from './step5-add-tracks.component';

describe('Step5AddTracksComponent', () => {
  let component: Step5AddTracksComponent;
  let fixture: ComponentFixture<Step5AddTracksComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Step5AddTracksComponent]
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(Step5AddTracksComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
