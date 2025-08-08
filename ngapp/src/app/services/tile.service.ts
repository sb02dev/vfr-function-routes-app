import { HttpClient } from '@angular/common/http';
import { Injectable, OnDestroy } from '@angular/core';
import { environment } from '../../environments/environment';

@Injectable({
    providedIn: 'root',
})
export class TileService implements OnDestroy {

    private tileCache = new Map<string, ImageBitmap>();
    
    constructor(private http: HttpClient) { }
    
    async getTile(tilesetName: string, dpi: number, x: number, y: number): Promise<ImageBitmap | undefined> {
        var blob: Blob | undefined;
        const cachekey = `${tilesetName}-${dpi}-${x}-${y}`;
        // try memory cache
        const memcached = this.tileCache.get(cachekey);
        if (memcached) return memcached;
        // TODO: try indexeddb-cache
        // download from server (maybe hits browser http cache)
        blob = await this.http.get(`${environment.API_URL}/tile/${tilesetName}/${dpi}/${x}/${y}`, { responseType: 'blob'}).toPromise();
        // TODO: save to indexeddb-cache
        // if no data, return nothing sadly
        if (!blob) return undefined;
        // create bitmap and put to memcache
        const bitmap = await createImageBitmap(blob);
        this.tileCache.set(cachekey, bitmap);
        // we finally have a bitmap
        return bitmap;
    }

    ngOnDestroy(): void {
        // clear the tilecache and release the URLs
        this.tileCache.forEach((bitmap: ImageBitmap, key: string) => {
            bitmap.close();
        });
        this.tileCache.clear();
    }
}
