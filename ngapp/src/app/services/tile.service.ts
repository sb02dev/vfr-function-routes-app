import { HttpClient } from '@angular/common/http';
import { Injectable, OnDestroy } from '@angular/core';
import { environment } from '../../environments/environment';
import { tap } from 'rxjs';

@Injectable({
    providedIn: 'root',
})
export class TileService implements OnDestroy {

    private tileCache = new Map<string, ImageBitmap>();
    private tileDownloads = new Map<string, (blob: Blob) => void>();
    
    constructor(private http: HttpClient) { }
    
    async getTile(tilesetName: string, dpi: number, x: number, y: number, cbDownloaded: (blob: Blob) => void): Promise<ImageBitmap | undefined> {
        const cachekey = `${tilesetName}-${dpi}-${x}-${y}`;
        // try memory cache
        const memcached = this.tileCache.get(cachekey);
        if (memcached) {
            return memcached;
        }
        // TODO: try indexeddb-cache
        // if already downloading we return nothing, we do not wait
        const isDownloading = this.tileDownloads.has(cachekey);
        if (isDownloading) {
            return undefined;
        }
        // start downloading from server (maybe hits browser http cache)
        this.tileDownloads.set(cachekey, cbDownloaded);
        this.http.get(`${environment.API_URL}/tile/${tilesetName}/${dpi}/${x}/${y}`, { responseType: 'blob' }).subscribe(async (value: Blob) => {
            // TODO: save to indexeddb-cache
            // save downloaded image to memory cache
            if (value) {
                // create bitmap and put to memcache
                const bitmap = await createImageBitmap(value);
                this.tileCache.set(cachekey, bitmap);
            }
            // mark as not downloading (it will hit memory cache anyway)
            this.tileDownloads.delete(cachekey);
            // call callback on successful download
            if (cbDownloaded) {
                cbDownloaded(value);
            }
        });
        // at this point we still have no tile downloaded
        return undefined;
    }

    ngOnDestroy(): void {
        // clear the tilecache and release the URLs
        this.tileCache.forEach((bitmap: ImageBitmap, key: string) => {
            bitmap.close();
        });
        this.tileCache.clear();
    }
}
