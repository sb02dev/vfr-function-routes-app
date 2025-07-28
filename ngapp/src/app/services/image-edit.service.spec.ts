import { TestBed } from '@angular/core/testing';

import { ImageEditService } from './image-edit.service';

describe('ImageEditService', () => {
  let service: ImageEditService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(ImageEditService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
